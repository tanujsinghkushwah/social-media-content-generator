"""Rate limiter for Twitter API to track and prevent exceeding free tier limits."""

import json
import os
from datetime import datetime, timedelta
from typing import Optional


class TwitterRateLimiter:
    """Tracks Twitter API usage to prevent hitting rate limits."""
    
    # X Free tier limits
    MONTHLY_POST_LIMIT = 500
    DAILY_POST_LIMIT = 17  # ~500/30 days, being conservative
    
    def __init__(self, storage_path: Optional[str] = None):
        """Initialize rate limiter with optional custom storage path."""
        if storage_path is None:
            # Store in project root by default
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_path = os.path.join(project_root, '.twitter_usage.json')
        
        self.storage_path = storage_path
        self.usage_data = self._load_usage()
    
    def _load_usage(self) -> dict:
        """Load usage data from storage file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    # Validate and migrate old data format if needed
                    if 'posts' not in data:
                        data['posts'] = []
                    if 'monthly_reset' not in data:
                        data['monthly_reset'] = self._get_month_start().isoformat()
                    if 'rate_limit_lockout' not in data:
                        data['rate_limit_lockout'] = None
                    return data
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load usage data: {e}")
        
        # Return fresh data structure
        return {
            'posts': [],
            'monthly_reset': self._get_month_start().isoformat(),
            'rate_limit_lockout': None
        }
    
    def _save_usage(self):
        """Save usage data to storage file."""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.usage_data, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save usage data: {e}")
    
    def _get_month_start(self) -> datetime:
        """Get the start of the current month."""
        now = datetime.now()
        return datetime(now.year, now.month, 1)
    
    def _get_today_start(self) -> datetime:
        """Get the start of today."""
        now = datetime.now()
        return datetime(now.year, now.month, now.day)
    
    def _clean_old_posts(self):
        """Remove posts older than current month."""
        month_start = self._get_month_start()
        stored_reset = datetime.fromisoformat(self.usage_data['monthly_reset'])
        
        # If we're in a new month, reset the counter
        if month_start > stored_reset:
            print(f"New month detected. Resetting post counter.")
            self.usage_data['posts'] = []
            self.usage_data['monthly_reset'] = month_start.isoformat()
            self._save_usage()
        else:
            # Clean posts older than this month
            valid_posts = []
            for post in self.usage_data['posts']:
                post_time = datetime.fromisoformat(post['timestamp'])
                if post_time >= month_start:
                    valid_posts.append(post)
            
            if len(valid_posts) != len(self.usage_data['posts']):
                self.usage_data['posts'] = valid_posts
                self._save_usage()
    
    def get_monthly_usage(self) -> int:
        """Get the number of posts made this month."""
        self._clean_old_posts()
        return len(self.usage_data['posts'])
    
    def get_daily_usage(self) -> int:
        """Get the number of posts made today."""
        today_start = self._get_today_start()
        count = 0
        for post in self.usage_data['posts']:
            post_time = datetime.fromisoformat(post['timestamp'])
            if post_time >= today_start:
                count += 1
        return count
    
    def get_remaining_posts(self) -> dict:
        """Get remaining posts for today and this month."""
        self._clean_old_posts()
        monthly_used = self.get_monthly_usage()
        daily_used = self.get_daily_usage()
        
        return {
            'monthly_remaining': max(0, self.MONTHLY_POST_LIMIT - monthly_used),
            'monthly_used': monthly_used,
            'monthly_limit': self.MONTHLY_POST_LIMIT,
            'daily_remaining': max(0, self.DAILY_POST_LIMIT - daily_used),
            'daily_used': daily_used,
            'daily_limit': self.DAILY_POST_LIMIT
        }
    
    def set_rate_limit_lockout(self, lockout_hours: int = 24):
        """
        Set a rate limit lockout after receiving a 429 from Twitter.
        
        Args:
            lockout_hours: Hours to wait before trying again (default: 24)
        """
        lockout_until = datetime.now() + timedelta(hours=lockout_hours)
        self.usage_data['rate_limit_lockout'] = lockout_until.isoformat()
        self._save_usage()
        print(f"🔒 Rate limit lockout set until {lockout_until.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def clear_lockout(self):
        """Manually clear a rate limit lockout."""
        self.usage_data['rate_limit_lockout'] = None
        self._save_usage()
        print("🔓 Rate limit lockout cleared.")
    
    def is_locked_out(self) -> tuple[bool, Optional[datetime]]:
        """
        Check if we're in a rate limit lockout period.
        
        Returns:
            Tuple of (is_locked: bool, lockout_until: datetime or None)
        """
        lockout = self.usage_data.get('rate_limit_lockout')
        if lockout is None:
            return False, None
        
        lockout_until = datetime.fromisoformat(lockout)
        if datetime.now() >= lockout_until:
            # Lockout expired, clear it
            self.usage_data['rate_limit_lockout'] = None
            self._save_usage()
            return False, None
        
        return True, lockout_until
    
    def can_post(self, warn_threshold: int = 50) -> tuple[bool, str]:
        """
        Check if posting is allowed and return status message.
        
        Args:
            warn_threshold: Warn when remaining posts fall below this number
            
        Returns:
            Tuple of (can_post: bool, message: str)
        """
        # Check for rate limit lockout first
        is_locked, lockout_until = self.is_locked_out()
        if is_locked and lockout_until:
            time_remaining = lockout_until - datetime.now()
            hours = int(time_remaining.total_seconds() // 3600)
            minutes = int((time_remaining.total_seconds() % 3600) // 60)
            return False, (
                f"🔒 Rate limit lockout active! Twitter returned 429 earlier. "
                f"Wait {hours}h {minutes}m (until {lockout_until.strftime('%H:%M:%S')}) before trying again."
            )
        
        remaining = self.get_remaining_posts()
        
        # Check monthly limit
        if remaining['monthly_remaining'] <= 0:
            return False, (
                f"❌ Monthly limit reached! Used {remaining['monthly_used']}/{remaining['monthly_limit']} posts. "
                f"Resets on {self._get_next_month_start().strftime('%B %d, %Y')}."
            )
        
        # Check daily limit (soft limit to spread usage)
        if remaining['daily_remaining'] <= 0:
            return False, (
                f"[!] Daily limit reached! Posted {remaining['daily_used']}/{remaining['daily_limit']} today. "
                f"You still have {remaining['monthly_remaining']} posts this month. "
                f"Consider waiting until tomorrow to spread usage."
            )
        
        # Warning if approaching limit
        if remaining['monthly_remaining'] <= warn_threshold:
            message = (
                f"[!] Warning: Only {remaining['monthly_remaining']} posts remaining this month! "
                f"Used {remaining['monthly_used']}/{remaining['monthly_limit']}."
            )
        else:
            message = (
                f"[OK] Rate limit OK. "
                f"Monthly: {remaining['monthly_used']}/{remaining['monthly_limit']} used, "
                f"Daily: {remaining['daily_used']}/{remaining['daily_limit']} used."
            )
        
        return True, message
    
    def _get_next_month_start(self) -> datetime:
        """Get the start of next month."""
        now = datetime.now()
        if now.month == 12:
            return datetime(now.year + 1, 1, 1)
        return datetime(now.year, now.month + 1, 1)
    
    def record_post(self, tweet_id: str):
        """Record a successful post."""
        self._clean_old_posts()
        
        self.usage_data['posts'].append({
            'tweet_id': tweet_id,
            'timestamp': datetime.now().isoformat()
        })
        
        self._save_usage()
        
        remaining = self.get_remaining_posts()
        print(f"📊 Post recorded. Monthly: {remaining['monthly_used']}/{remaining['monthly_limit']}, "
              f"Daily: {remaining['daily_used']}/{remaining['daily_limit']}")
    
    def get_usage_report(self) -> str:
        """Get a formatted usage report."""
        remaining = self.get_remaining_posts()
        next_reset = self._get_next_month_start()
        
        report = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Twitter API Usage Report (Free Tier)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monthly Usage:  {remaining['monthly_used']:>3} / {remaining['monthly_limit']} posts
Monthly Left:   {remaining['monthly_remaining']:>3} posts
Daily Usage:    {remaining['daily_used']:>3} / {remaining['daily_limit']} posts
Daily Left:     {remaining['daily_remaining']:>3} posts
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Next Reset:     {next_reset.strftime('%B %d, %Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return report

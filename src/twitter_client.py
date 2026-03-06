"""Twitter API client for posting tweets and interacting with Twitter."""

from typing import Optional

import time
import tweepy
from src.rate_limiter import TwitterRateLimiter


class TwitterClient:
    """Client for Twitter API operations."""
    
    def __init__(
        self,
        api_key: str,
        api_key_secret: str,
        access_token: str,
        access_token_secret: str,
        bearer_token: Optional[str] = None,
    ):
        """Initialize Twitter client with credentials."""
        # Initialize rate limiter
        self.rate_limiter = TwitterRateLimiter()
        
        # Initialize Twitter client (v2)
        # We DO NOT pass bearer_token here to force Tweepy to use User Context (OAuth 1.0a)
        # which is required for posting on most Free/Basic accounts.
        self.client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_key_secret,
            access_token=access_token,
            access_token_secret=access_token_secret
        )
        
        # Initialize Twitter API v1.1 for media uploads
        auth = tweepy.OAuth1UserHandler(
            api_key, api_key_secret, access_token, access_token_secret
        )
        self.api = tweepy.API(auth)
        
        # Get own user ID
        try:
            self.me = self.client.get_me()
            me_data = getattr(self.me, "data", None)
            self.user_id = me_data.id if me_data is not None else None
            username = getattr(me_data, "username", None) if me_data else None
            print(f"Twitter client initialized for user: {username}")
        except Exception as e:
            print(f"Warning: Could not get user information: {e}")
            print("Some features like mention tracking may not work properly.")
            self.user_id = None
    
    def search_tweets(self, query: str, max_results: int = 10):
        """Search for tweets based on keywords."""
        try:
            # Exclude retweets and replies for better results
            formatted_query = f"{query} -is:retweet -is:reply"
            
            # Search for recent tweets
            tweets = self.client.search_recent_tweets(
                query=formatted_query,
                max_results=max_results,
                tweet_fields=['created_at', 'author_id', 'conversation_id']
            )
            
            tweets_data = getattr(tweets, "data", None)
            if not tweets_data:
                print(f"No tweets found for query: {query}")
                return []
            return tweets_data
        except Exception as e:
            print(f"Error searching tweets: {e}")
            return []
    
    def get_mentions(self, since_id: Optional[int] = None):
        """Get mentions directed at the bot."""
        try:
            # Get mentions
            mentions = self.client.get_users_mentions(
                id=self.user_id,
                since_id=since_id,
                tweet_fields=['created_at', 'author_id', 'conversation_id']
            )
            
            mentions_data = getattr(mentions, "data", None)
            if not mentions_data:
                print("No new mentions found")
                return []
            return mentions_data
        except Exception as e:
            print(f"Error getting mentions: {e}")
            return []
    
    def post_tweet(
        self,
        text: str,
        media_ids: Optional[list] = None,
        max_retries: int = 3,
        retry_delay: int = 10,
    ):
        """Post a tweet with optional media."""
        # Check rate limits before posting
        can_post, message = self.rate_limiter.can_post()
        print(message)
        
        if not can_post:
            print("Skipping post due to rate limit.")
            return None
        
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Log the full tweet content for debugging
                print(f"DEBUG: Full tweet text ({len(text)} chars):\n---\n{text}\n---")
                print(f"DEBUG: Media IDs: {media_ids}")
                
                if media_ids:
                    media_ids_str = [str(m) for m in media_ids]
                    response = self.client.create_tweet(
                        text=text,
                        media_ids=media_ids_str
                    )
                else:
                    response = self.client.create_tweet(text=text)

                response_data = getattr(response, "data", None)
                tweet_id = response_data["id"] if response_data else None
                print(f"Tweet posted successfully: {tweet_id}")
                
                # Record successful post for rate limiting
                self.rate_limiter.record_post(str(tweet_id))
                
                return tweet_id
            except Exception as e:
                error_str = str(e)
                retry_count += 1
                
                # Check if it's a rate limit error
                if '429' in error_str or 'Too Many Requests' in error_str:
                    print(f"[!] Rate limit hit from Twitter API!")
                    print(self.rate_limiter.get_usage_report())
                    
                    # On final retry, set lockout to prevent further wasted calls
                    if retry_count >= max_retries:
                        self.rate_limiter.set_rate_limit_lockout(lockout_hours=24)
                
                if retry_count < max_retries:
                    print(f"Error posting tweet: {e}. Retrying in {retry_delay} seconds... (Attempt {retry_count}/{max_retries})")
                    err_resp = getattr(e, "response", None)
                    if err_resp is not None:
                        print(f"DEBUG: API Error Detail: {getattr(err_resp, 'text', '')}")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to post tweet after {max_retries} attempts: {e}")
                    err_resp = getattr(e, "response", None)
                    if err_resp is not None:
                        print(f"DEBUG: Final API Error Detail: {getattr(err_resp, 'text', '')}")
                    return None
    
    def reply_to_tweet(self, tweet_id: int, text: str, max_retries: int = 3, retry_delay: int = 10):
        """Reply to a specific tweet."""
        # Check rate limits before replying
        can_post, message = self.rate_limiter.can_post()
        print(message)
        
        if not can_post:
            print("Skipping reply due to rate limit.")
            return None
        
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                response = self.client.create_tweet(
                    text=text,
                    in_reply_to_tweet_id=tweet_id
                )
                response_data = getattr(response, "data", None)
                reply_id = response_data["id"] if response_data else None
                print(f"Reply posted successfully: {reply_id}")
                
                # Record successful reply for rate limiting
                self.rate_limiter.record_post(str(reply_id))
                
                return reply_id
            except Exception as e:
                error_str = str(e)
                retry_count += 1
                
                # Check if it's a rate limit error
                if '429' in error_str or 'Too Many Requests' in error_str:
                    print(f"[!] Rate limit hit from Twitter API!")
                    print(self.rate_limiter.get_usage_report())
                    
                    # On final retry, set lockout to prevent further wasted calls
                    if retry_count >= max_retries:
                        self.rate_limiter.set_rate_limit_lockout(lockout_hours=24)
                
                if retry_count < max_retries:
                    print(f"Error replying to tweet: {e}. Retrying in {retry_delay} seconds... (Attempt {retry_count}/{max_retries})")
                    time.sleep(retry_delay)
                else:
                    print(f"Failed to reply to tweet after {max_retries} attempts: {e}")
                    return None
    
    def upload_media(self, image_buffer, filename: str = 'image.jpg'):
        """Upload media to Twitter from buffer."""
        try:
            media = self.api.media_upload(filename=filename, file=image_buffer)
            return media.media_id_string
        except Exception as e:
            print(f"Error uploading media: {e}")
            return None
    
    def upload_media_from_file(self, filepath: str):
        """Upload media to Twitter from file path."""
        try:
            media = self.api.media_upload(filename=filepath)
            print(f"Media uploaded! ID: {media.media_id_string}")
            return media.media_id_string
        except Exception as e:
            print(f"Error uploading media from file: {e}")
            return None
    
    def get_tweet(self, tweet_id: int):
        """Get a tweet by ID."""
        try:
            response = self.client.get_tweet(tweet_id)
            tweet = getattr(response, "data", None)
            return tweet
        except Exception as e:
            print(f"Error getting tweet: {e}")
            return None





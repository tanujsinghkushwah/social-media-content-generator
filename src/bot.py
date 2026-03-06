"""Main bot class orchestrating Twitter bot functionality."""

from typing import Optional
import random
from src.twitter_client import TwitterClient
from src.ai_service import AIService
from src.image_generator import ImageGenerator
from src.constants import KEYWORDS


class GenieTweetBot:
    """AskMeGenie Twitter bot with AI-powered content generation."""
    
    def __init__(self, config: dict):
        """Initialize bot with configuration."""
        self.twitter_client = TwitterClient(
            api_key=config['API_KEY'],
            api_key_secret=config['API_KEY_SECRET'],
            access_token=config['ACCESS_TOKEN'],
            access_token_secret=config['ACCESS_TOKEN_SECRET'],
            bearer_token=config['BEARER_TOKEN']
        )

        self.ai_service = AIService(
            api_key=str(config.get("OPENROUTER_API", "")),
            model_name=str(config.get("CONTENT_MODEL", "arcee-ai/trinity-large-preview:free")),
        )
        self.image_generator = ImageGenerator(
            cloudflare_account_id=config.get("CLOUDFLARE_ACCOUNT_ID"),
            cloudflare_api_token=config.get("CLOUDFLARE_API_TOKEN"),
            model_name=config.get("IMAGE_MODEL"),
        )
    

    
    def check_rate_limits(self) -> bool:
        """Check if bot interactions are allowed by rate limits."""
        can_post, message = self.twitter_client.rate_limiter.can_post()
        if not can_post:
            print(message)
            return False
        return True

    def post_tweet(self, text: str, with_image: bool = False, image_topic: Optional[str] = None, image_title: Optional[str] = None):
        """Post a tweet with optional AI-generated image."""
        print(f"DEBUG: Original generated text: {text}")
        
        website_link = "\n\nLearn more at interviewgenie.net"
        tweet_text = text + website_link
        
        # Twitter counts all URLs as 23 characters regardless of length.
        # To be safe and account for weighting/emojis, we'll aim for 260 total.
        limit = 260
        if len(tweet_text) > limit:
            print(f"Warning: Tweet text length ({len(tweet_text)}) exceeds {limit}. Truncating...")
            # Truncate 'text' so that text + website_link fits in limit
            available_space = limit - len(website_link) - 3  # -3 for '...'
            tweet_text = text[:available_space] + "..." + website_link
        
        print(f"DEBUG: Final tweet content to post ({len(tweet_text)} chars):\n{tweet_text}")
        
        if with_image and image_topic:
            # Generate image
            print(f"Generating image for topic: {image_topic}")
            
            if not image_title:
                image_title = image_topic
            image_prompt = self.ai_service.generate_image_prompt(image_topic, tweet_content=text)
            
            if not image_prompt:
                print("Image prompt generation failed, posting text-only tweet")
                return self.twitter_client.post_tweet(tweet_text)

            img_buffer = self.image_generator.generate_image(
                image_prompt,
                fallback_generator=self.image_generator.create_tech_themed_image
            )
            
            if img_buffer:
                print("Uploading image to Twitter...")
                # Use file path for upload (more reliable than buffer)
                media_id = self.twitter_client.upload_media_from_file("generated_image.jpg")
                if media_id:
                    print(f"DEBUG: Final tweet text to post: '{tweet_text[:50]}...'")
                    return self.twitter_client.post_tweet(tweet_text, media_ids=[media_id])
                else:
                    print("Media upload failed, posting text-only tweet")
                    return self.twitter_client.post_tweet(tweet_text)
            else:
                print("Image generation failed, posting text-only tweet")
                return self.twitter_client.post_tweet(tweet_text)
        else:
            return self.twitter_client.post_tweet(tweet_text)
    
    def interact_with_keyword_tweets(self):
        """Find and interact with tweets containing keywords."""
        if not self.check_rate_limits():
            return

        print(f"Searching for tweets with keywords...")
        keyword = random.choice(KEYWORDS)
        
        tweets = self.twitter_client.search_tweets(keyword, max_results=5)
        
        if not tweets:
            return
        tweet = random.choice(tweets)

        original_tweet = self.twitter_client.get_tweet(tweet.id)
        if not original_tweet:
            return
        
        tweet_text = original_tweet.text
        
        prompt = f"""
        You are AskMeGenie, a helpful AI assistant specializing in software engineering, tech trends, and career advice.
        
        Here's a tweet: "{tweet_text}"
        
        Craft a thoughtful, informative reply that demonstrates expertise while being humble and curious. 
        Make it conversational and human-like, as if written by a tech professional.
        Add a touch of personality and warmth to it.
        Keep it under 240 characters and make it engaging without using hashtags.
        
        Don't use phrases like "As an AI" or anything that reveals you're an AI.
        Do not use asterisks for emphasis (like *word* or *phrase*) in your response.
        """
        
        response = self.ai_service.generate_response(prompt, conversation_id=str(tweet.id))
        
        if response:
            self.twitter_client.reply_to_tweet(tweet.id, response)
            print(f"Interacted with tweet: {tweet.id}")
    
    def respond_to_mentions(self, since_id: Optional[int] = None):
        """Respond to mentions of the bot."""
        if not self.check_rate_limits():
            return since_id

        print("Checking for mentions...")
        mentions = self.twitter_client.get_mentions(since_id=since_id)
        
        if not mentions:
            return since_id
        
        newest_id = since_id
        
        for mention in mentions:
            if newest_id is None or mention.id > newest_id:
                newest_id = mention.id
            tweet = self.twitter_client.get_tweet(mention.id)
            if not tweet:
                continue
            
            tweet_text = tweet.text
            prompt = f"""
            You are AskMeGenie, a helpful AI assistant specializing in software engineering, tech trends, and career advice.
            
            A user has mentioned you in this tweet: "{tweet_text}"
            
            Respond in a casual, friendly tone like a tech professional would. Be concise (under 240 characters).
            If they're asking a question, provide a clear answer.
            If unclear, ask for clarification.
            
            Don't use phrases like "As an AI" or anything that reveals you're an AI.
            Make it sound natural like a human tech expert's tweet.
            Do not use asterisks for emphasis (like *word* or *phrase*) in your response.
            """
            
            response = self.ai_service.generate_response(prompt, conversation_id=str(mention.id))
            if response:
                self.twitter_client.reply_to_tweet(mention.id, response)
                print(f"Responded to mention: {mention.id}")
        
        return newest_id
    
    def generate_tech_post(self):
        """Generate and post content about latest tech trends with engaging images."""
        if not self.check_rate_limits():
            return

        print("Generating tech post...")
        with_image = True
        base_topic = random.choice(KEYWORDS)

        topic_prompt = f"""
        Based on the general topic '{base_topic}', generate a specific, current tech subtopic 
        that would be interesting to software engineers and tech professionals in the current year.
        Your response should be ONLY the specific topic name in 3-5 words, nothing else.
        """
        
        specific_topic = self.ai_service.generate_response(topic_prompt)
        if not specific_topic:
            specific_topic = base_topic
        specific_topic = specific_topic.strip().strip('"\'.,;:')
        print(f"Selected specific tech topic: {specific_topic}")

        post_prompt = f"""
        You're a tech thought leader posting daily on X about software engineering life.

        Craft a viral tweet on '{specific_topic}' that hooks all software engineers (frontend, backend, full-stack, etc.):

        - Open with bold/contrarian hook on a universal dev pain (e.g., "Everyone chases X, but...")
        - Drop 1 unexpected insight from real SDE experience (keep <5 sentences, simple words)
        - End with reply bait: question like "What's your take?" or polarizing takeaway
        - STRICTLY UNDER 200 characters (total budget is 280, including links)
        - Short, punchy sentences.
        - No hashtags, no AI mentions, no *emphasis*
        """
        
        post_content = self.ai_service.generate_response(post_prompt)
        
        if post_content:
            self.post_tweet(post_content, with_image=with_image, image_topic=specific_topic, image_title=specific_topic)
            print("Tech post generated and posted with image")





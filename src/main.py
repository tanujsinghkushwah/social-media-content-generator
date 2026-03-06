"""Social Media Content Generator entry point."""

from src.config import load_config
from src.pipeline import ContentPipeline


def run_pipeline():
    """Run the content generation pipeline."""
    config = load_config()
    post_count = config.get("POST_COUNT", 3)

    pipeline = ContentPipeline(config)
    pipeline.run(post_count)


if __name__ == "__main__":
    run_pipeline()

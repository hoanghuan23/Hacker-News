class HackerNewsCrawler:
    """Extension point for full post/comment crawling in later versions."""

    def run_once(self) -> None:
        raise NotImplementedError("Full Hacker News crawling is not implemented in v1.")

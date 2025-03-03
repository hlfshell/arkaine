from arkaine.utils.website import Website


def register_youtube_plugin():
    # Ensure that we have the necessary imports
    try:
        from pytube import YouTube  # noqa: F401
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: F401
    except ImportError:
        raise ImportError(
            "Youtube plugin requires pytube==15.0.0 and "
            "youtube-transcript-api==0.6.3"
        )

    Website.add_custom_domain_loader("youtube.com", load_youtube_content)


def load_youtube_content(website: Website):
    from pytube import YouTube
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        yt = YouTube(website.url)
        transcript = YouTubeTranscriptApi.get_transcript(
            yt.video_id, preserve_formatting=True
        )
    except Exception:  # noqa: B902
        # Fall back to default loader
        Website.load(website)
    try:
        title = yt.title
    except Exception:  # noqa: B902
        title = ""
    try:
        description = yt.description
    except Exception:  # noqa: B902
        description = ""

    content = f"Youtube - {title}\n{description}\n\n"
    content += "Video Transcript:\n"
    content += "".join([t["text"] for t in transcript])
    if not website.title:
        website.title = title
    if not website.snippet:
        website.snippet = description
    website.raw_content = content
    website.markdown = content

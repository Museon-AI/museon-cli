# Content Analyzer boundary

Use `museoncli content-analysis +run` for video platform URLs, Museon video media, or local video files. It is a write/async command, so inspect its schema, state the analysis job to be created, and obtain separate approval.

Static images, carousels, and slideshows do not use the video-only Content Analyzer path. Analyze visuals with research tools or extract reusable formats with `museon-content-workflow-assets`.

When a completed analysis returns a `share_url`, include it so the user can inspect the full result.

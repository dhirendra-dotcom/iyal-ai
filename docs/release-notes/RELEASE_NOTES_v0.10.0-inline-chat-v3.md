# IYAL.ai v0.10.0 Inline Chat v3

- Keeps generated STL and illustrative preview in the conversation stream.
- Adds a fast per-instance session-owner cache for artifact reads.
- Artifact content no longer repeats a managed Vertex session lookup for the active session.
- Falls back to the authoritative session service after restart/cache miss.
- Adds `artifact_content_served` timing logs.
- Extends the lightweight STL fetch timeout to 45 seconds as a fallback.
- Keeps the dependency baseline pinned to the user-confirmed versions.

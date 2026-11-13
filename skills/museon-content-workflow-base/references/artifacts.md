# Artifact lifecycle

## Mental model

Use an Artifact for something the user will keep, share, edit, download, schedule, or revisit. The runtime `artifact-authoring` Business Skill owns report structure. Validation checks the local contract without network calls. Upload creates/replaces the hosted artifact; share/unshare changes public reach, not organization ownership.

Ready-made `ref` values preserve live cards. Raw TikTok, Instagram, and YouTube URLs can represent player embeds.

## Shortcuts

| Stage | Start with |
| --- | --- |
| Structure | `museoncli skills +get` |
| Contract check | `museoncli artifacts +validate` |
| Hosting | `museoncli artifacts +upload` |
| Find an existing artifact | `museoncli artifacts +list --search <title words>` (add `--all` for every page) |
| Read one (Markdown, or download_url for a file) | `museoncli artifacts +get --id <artifact_id>` |

## DON'T

- **DON'T** skip the current `artifact-authoring` Business Skill.
- **DON'T** edit or reconstruct opaque `ref` values.
- **DON'T** put several generation refs inline when each should render as a card.
- **DON'T** confuse public revocation with deletion of the organization artifact. There is no delete command: the API cannot delete an artifact.
- **DON'T** re-upload to update a report you have not read: `+list` then `+get` first, and replace it with `+upload --artifact-id`.

## Relationships

Source-domain Skills own correctness and provenance; this Skill owns durable presentation and access state.

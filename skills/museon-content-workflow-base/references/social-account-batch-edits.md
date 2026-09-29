# Profile and avatar edits

Use `+draft-profile-edit` to review proposed display name, bio, or avatar changes before submission.
Use `+submit-profile-edit` for one account and `+bulk-submit-profile-edit` for several accounts in one
request. A submit receipt is not completion; poll `+get-profile-edit` and report per-account failures.

Avatar generation uses `+bulk-generate-avatars` followed by `+get-avatar-generation`. Feed only
successful avatar results into a profile edit. Do not use profile commands to change publish schedules,
asset pools, or HireAICreator assignments.

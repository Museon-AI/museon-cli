# Profile and avatar edits

Use `+profile-edit-draft` to review proposed display name, bio, or avatar changes before submission.
Use `+profile-edit-submit` for one account and `+profile-edit-batch-submit` for several accounts in one
request. A submit receipt is not completion; poll `+profile-edit-status` and report per-account failures.

Avatar generation uses `+avatar-generate-batch` followed by `+avatar-generate-status`. Feed only
successful avatar results into a profile edit. Do not use profile commands to change publish schedules,
asset pools, or HireAICreator assignments.

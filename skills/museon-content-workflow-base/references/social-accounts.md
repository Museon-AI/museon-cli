# Retained account state

`+list` resolves canonical account IDs; `+get` verifies one account. A connection link is only an
authorization request until `+get-connect-link` reports its terminal result. `+connect-adb` and
`+get-stream-url` address the phone already bound to that account and do not change its business ownership.

`+connect-adb` waits up to about two minutes for a cold phone by itself. If it still ends with
`server_code: CLOUD_PHONE_BOOTING`, the phone is booting and stays on: run the same command again once
before reporting it as a blocker. A repeat does not start the phone twice.

Performance responses carry provenance. Relay whether data came from official/managed analytics or
public fallback, and do not turn a missing page into a claim that the account has no history.

HireAICreator account assignment, plan capacity, generation, scheduling, and delivery are owned by `hireaicreator`.

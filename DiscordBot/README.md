Current functionality:
- Auto-flag message to mod channel iff the message if any toxicity level according to perspective > 0.5. This includes sending an innocuous message and editing it to something bad. The bot will react to the message with 🤬
- Mock the user flow. After the user completes the flow, generate a report and immediately forward it to mod channel (can be later changed to on-command forwarding based on condition at location). The bot will react to the message with 🛑
- Stop a user from submitting multiple reports on the same message  (can add more conditions later)

Extra packages to install:
- `unidecode`
  
Questions:
- only send auto-flagged message to moderator for unconfident predictions
- TODO:only send the message at the top of the PQ, and send another when the current one HAS BEEN PROCESSED?
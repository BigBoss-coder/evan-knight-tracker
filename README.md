# Evan Knight Round Tracker

This tracker checks Evan Knight's PGA TOUR Americas leaderboard data and sends a Telegram message only after his round is complete.

## What it does

- Checks Evan Knight's PGA TOUR Americas leaderboard data.
- Looks for player ID `56731`.
- Sends one alert per completed tournament round.
- Remembers sent alerts in `state/evan_knight_state.json` so repeat checks do not spam you.
- Runs locally or on a free scheduled GitHub Actions workflow.

## Notification format

The alert includes:

- tournament name
- round number
- position
- today's round score
- total score
- thru/status
- round scores
- leader information when available
- leaderboard link

## Telegram setup

Telegram is the recommended free notification channel.

1. Open Telegram and message `@BotFather`.
2. Send `/newbot` and follow the prompts.
3. Copy the bot token.
4. Start a chat with your new bot and send it any message.
5. Visit this URL in your browser, replacing `<TOKEN>` with your token:

   `https://api.telegram.org/bot<TOKEN>/getUpdates`

6. Find your chat ID in the response. It is usually under `message.chat.id`.

To send alerts to multiple private chats, separate chat IDs with commas:

```text
8504757036,1111111111,2222222222
```

Each person must first open your bot in Telegram and send it `/start`. Then visit:

```text
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Look for each person's `chat.id`.

You can also use a Telegram group instead:

1. Create a Telegram group.
2. Add your bot to the group.
3. Send a message in the group.
4. Open the `getUpdates` URL again.
5. Use the group's `chat.id` as `TELEGRAM_CHAT_ID`.

Group chat IDs usually start with a minus sign, like `-1001234567890`.

## GitHub setup

Create a GitHub repo for this folder, then add these repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The workflow is already included at `.github/workflows/evan-knight-tracker.yml`.

In GitHub, also check:

- Repository Settings -> Actions -> General -> Workflow permissions
- Choose "Read and write permissions"

That lets the workflow save the tiny `state/` file after each run.

## Local test

Copy the example environment file:

```bash
cp .env.example .env
```

Fill in the Telegram values, then run:

```bash
python3 tracker.py
```

To test without sending Telegram messages:

```bash
DRY_RUN=true python3 tracker.py
```

## Tracking tournaments outside PGA TOUR

This first version automatically tracks Evan when he appears on the PGA TOUR Americas leaderboard.

For tournaments that are not on PGA TOUR pages, add the leaderboard URL to:

```bash
EXTRA_LEADERBOARD_URLS
```

in `.env` or the GitHub workflow environment. This works best for pages that expose structured leaderboard data. Sites like Golf Genius, BlueGolf, Clippd, or one-off tournament pages may need a small adapter because they all publish scores differently.

The practical plan is:

- Use this tracker for PGA TOUR Americas.
- Add known non-PGA tournament URLs as you find them.
- Build a source adapter for any site Evan plays on repeatedly.

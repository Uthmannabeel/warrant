# Warrant — Setup & Connectivity Test (Phase 0)

The goal of Phase 0 is to **prove one thing before we build anything else**: that Warrant can
run a search inside Splunk *through the MCP Server* and get data back. If that round-trip
works, every other phase is downstream of it. This is our de-risking step.

You'll do parts **A–C** (account + installs, mostly clicking). I'll wire part **D** (the code).
Estimated time for you: ~45–60 minutes.

---

## A. Create your Splunk environment

You have two options. **Option 1 (Splunk Cloud trial)** is easiest and matches how the
hackathon expects MCP to be used.

### Option 1 — Splunk Cloud free trial (recommended)
1. Go to <https://www.splunk.com/en_us/download.html> and start the **Splunk Cloud Platform
   free trial** (14 days). Use your email (`nraheemst@gmail.com`).
2. You'll get a URL like `https://<your-stack>.splunkcloud.com`. Save it — this is your
   **Splunk host**.
3. Log in and confirm you reach the Search & Reporting app.

### Option 2 — Splunk Enterprise on your PC (longer-lived, more setup)
1. Download **Splunk Enterprise** for Windows from the same page (60-day trial).
2. Also apply for the **6-month Developer License** via the Splunk Developer Program
   (<https://dev.splunk.com/enterprise/dev_license>) — this outlasts the hackathon.
3. Install, then open <http://localhost:8000> and log in with the admin account you set
   during install. Your **Splunk host** is `https://localhost:8089` (the management port).

> Pick ONE. Tell me which you chose — the connection details differ slightly and I'll match
> the code to it.

---

## B. Install the Splunk apps (from Splunkbase)

Inside Splunk: **Apps -> Find More Apps**, then search for and install each of these
(Splunk will ask you to log in with your splunk.com account):

1. **Splunk MCP Server** — this is the bridge Warrant connects to.
   (Splunkbase app 7931: <https://splunkbase.splunk.com/app/7931>)
2. **Splunk AI Assistant** — gives us the `saia_generate_spl` / `saia_ask_splunk_question`
   tools and access to **Hosted Models** (Foundation-sec, Cisco Deep Time Series).

After install, Splunk may ask to restart — let it.

---

## C. Turn on the MCP Server and get a token

1. Open the **Splunk MCP Server** app from the Apps menu.
2. In its setup page, **enable the server** and note the **MCP endpoint URL** it shows
   (looks like `https://<your-host>/.../mcp` over streamable HTTP).
3. Make sure these tools are toggled **ON**: `splunk_run_search`, the data-explore tools,
   and the `saia_*` tools (granular tool management lives in the app's settings).
4. Create an authentication token:
   - **Settings -> Tokens** (or **Settings -> Users and authentication -> Tokens**).
   - Click **New Token**, set the user to your admin user, audience `warrant`, and a long
     expiry. **Copy the token now — Splunk only shows it once.**
5. Confirm your user has the `mcp_tool_execute` capability and access to the `main` index
   (admin role has both by default).

---

## D. Wire Warrant to Splunk (I do this — you provide the values)

1. Copy `.env.example` to `.env` and fill in the four values below. **Never commit `.env`**
   (it's already git-ignored).

   ```
   SPLUNK_HOST=https://<your-stack>.splunkcloud.com
   SPLUNK_MCP_URL=https://<your-stack>.splunkcloud.com/.../mcp
   SPLUNK_TOKEN=<the token you copied in step C4>
   SPLUNK_INDEX=main
   ```

2. Create the Python environment and run the connectivity test:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python -m warrant.check_connection
   ```

3. **Success looks like this** — the script connects to the MCP Server, lists the available
   tools, runs `| makeresults count=3` through `splunk_run_search`, and prints 3 rows:

   ```
   [ok]  Connected to Splunk MCP Server
   [ok]  Tools available: splunk_run_search, saia_generate_spl, saia_ask_splunk_question, ...
   [ok]  Ran test search via MCP -> 3 rows returned
   PHASE 0 COMPLETE — Warrant can see Splunk.
   ```

If you see that, we're cleared to build Phase 1 (the sandbox flight-simulator).

---

## Troubleshooting
- **401 / auth error** -> token expired or wrong user; regenerate in step C4.
- **403 / capability error** -> your role is missing `mcp_tool_execute` or index access.
- **Connection refused / TLS error** -> on a corporate network, prefix the command with
  `$env:NODE_OPTIONS="--use-system-ca"` is for Node; for Python set
  `$env:SPLUNK_VERIFY_TLS="false"` (the test script reads this) to skip cert verification
  during local testing only.
- **Can't find a tool** -> re-check the granular tool toggles in step C3.

---

## What to send me when you're done with A–C
Just paste (here, not into git):
1. Which option you chose (Cloud trial or Enterprise local).
2. Your `SPLUNK_HOST` and `SPLUNK_MCP_URL`.
3. Confirmation you have a token (don't paste the token itself in chat — put it straight
   into `.env`).

Then I'll finish wiring part D and we run the connectivity test together.

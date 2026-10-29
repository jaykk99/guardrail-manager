# Guardrail Manager - deploy via the Cloudflare dashboard (no wrangler)

Two files from this folder are all you need:

- `worker.js` (51 KB, single file, UI inlined) - paste into the Worker editor
- `migration.sql` - paste into the D1 console

Order matters: database first, then the Worker, then bindings and secrets.

## 1. Create the D1 database

1. Cloudflare dashboard, pick the account (Jayomer1234@gmail.com's Account).
2. Left sidebar: **Storage & Databases** then **D1 SQL Database** then **Create**.
3. Name it exactly: `guardrail-manager`
4. Click **Create**.

## 2. Run the schema

1. Click the new `guardrail-manager` database to open it.
2. Open the **Console** tab.
3. Open `migration.sql` from this folder, copy ALL of it, paste it into the
   console, and run it (Execute).
4. It creates 5 tables: `settings`, `sessions`, `scan_cache`, `scan_files`,
   `audit_log`. No secrets go in the database.

## 3. Create the Worker and paste the code

1. Left sidebar: **Workers & Pages** then **Create** then **Worker**
   (the "Hello World" / start from scratch option).
2. Name it exactly: `guardrail-manager`
3. Click **Deploy** (this deploys the placeholder code).
4. On the Worker's page, click **Edit code**.
5. Select all in the editor, delete, and paste the ENTIRE contents of
   `worker.js` from this folder.
6. Click **Deploy** (top right, "Save and Deploy" on some screens).

## 4. Add the D1 binding (name must be exactly DB)

1. Back on the Worker's page: **Settings** then **Bindings** then **Add**.
2. Choose **D1 database**.
3. Variable name: `DB`  (exactly this, capital DB; the code reads `env.DB`)
4. Database: pick `guardrail-manager`.
5. **Deploy** / save.

## 5. Add the two secrets

Still in the Worker: **Settings** then **Variables and Secrets** then **Add**
for each of these. Type must be **Secret** (encrypted), not plain text.

1. Name `GITHUB_TOKEN`
   Value: a GitHub fine-grained personal access token with
   **Contents: Read and write** on **All repositories**, and no other
   permissions. Create it in GitHub: Settings, Developer settings,
   Personal access tokens, Fine-grained tokens.
2. Name `ACCESS_CODE`
   Value: the code you will type on the app's login screen. Your own
   value, pick it here and save it somewhere. If this secret is missing
   the app refuses every API call with 503 on purpose.

No other variables are needed: the GitHub owner defaults to `jaykk99`
inside the code.

After adding bindings and secrets, click **Deploy** once more if the
dashboard prompts for it.

## 6. Open it

URL format: `https://guardrail-manager.<your-subdomain>.workers.dev`

Your account's workers.dev subdomain is `jayomer1234` (same as the
mega-db shim), so the expected URL is:

`https://guardrail-manager.jayomer1234.workers.dev`

Log in with the ACCESS_CODE from step 5. Workers do not sleep, so the
app answers immediately at any hour.

## Quick checks if something is off

- Page loads but every action says "ACCESS_CODE secret is not set" (503):
  the ACCESS_CODE secret in step 5 did not save, or the Worker was not
  redeployed after adding it.
- Login works but repo actions error (500): the D1 binding is missing
  or not named exactly `DB`, or the schema in step 2 was not run.
- Scans come back empty or GitHub errors: the GITHUB_TOKEN secret is
  missing, expired, or lacks Contents read on the repos.

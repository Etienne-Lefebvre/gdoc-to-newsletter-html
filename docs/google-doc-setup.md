# Google Cloud + Docs setup

Step-by-step guide to getting the parser script authenticated against your own Google Docs. ~10-15 minutes start to finish.

## Overview

The parser needs to read Google Docs over the network. To do that, it uses a **service account** — basically a robot Google account with its own email address. You share each Doc with the service account email like you'd share with any human collaborator. The script authenticates as the service account using a JSON key file.

We use a service account rather than OAuth because: (1) no browser flow each month, (2) the script runs unattended, (3) collaborators don't need to grant their own permissions to anything.

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Click the project picker at the top → **New Project**.
3. Name it something like "Newsletter Automation". You don't need to attach a billing account; the Docs API has a generous free tier.

## 2. Enable the Google Docs API

1. With your new project selected, search the top bar for **Google Docs API**.
2. Click **Enable**. (Wait ~30 seconds for the activation to propagate.)

## 3. Create the service account

1. Left nav → **IAM & Admin → Service Accounts → Create Service Account**.
2. Name it `newsletter-parser` (or whatever).
3. Skip the optional "Grant this service account access to project" step — it doesn't need any project-level role to read shared Docs.
4. Click **Done**.

## 4. Generate a JSON key

On the service account's detail page:

1. **Keys** tab → **Add Key → Create new key → JSON**.
2. A `.json` file downloads automatically.
3. **Move the file somewhere safe and OUT of any synced folder** (not OneDrive, not Dropbox, not iCloud, not your Documents folder if that's synced). A good location on Windows: `C:\Users\YOU\.credentials\newsletter-parser.json`. On macOS/Linux: `~/.credentials/newsletter-parser.json`.

**Why this matters:** this JSON file is a non-expiring credential. If it leaks publicly (committed to git, synced to a shared folder, emailed to someone), anyone who finds it can read any Doc shared with the service account until you rotate the key.

## 4a. (Possibly required) Org policy override

If your organization is on Google Workspace, your org likely has the `iam.disableServiceAccountKeyCreation` policy enforced by default ("Secure by Default" rollout). You'll see this error when trying to create the key:

> Service account key creation is disabled. An Organization Policy that blocks service accounts key creation has been enforced on your organization.

To override it for just this project (recommended over disabling org-wide):

1. Make sure you have the **Organization Policy Administrator** role on the org. If you don't, grant it to yourself:
   - Switch the resource picker at the top to your **organization** (not the project).
   - **IAM & Admin → IAM** → find your user → ✏️ Edit → **Add another role** → search "Organization Policy Administrator" → Save.
2. Switch the resource picker back to your **project**.
3. **IAM & Admin → Organization Policies**.
4. Filter for `iam.disableServiceAccountKeyCreation` → click the policy.
5. **Manage Policy** → "Applies to" → **Override parent's policy** → add a rule with **Enforcement: Off** → **Set Policy**.
6. Wait 2–3 minutes for propagation, then retry step 4.

## 5. Copy the service account email

On the service account detail page, copy its email address. It looks like:
`newsletter-parser@newsletter-automation-123456.iam.gserviceaccount.com`

## 6. Share your Google Doc with the service account

1. Open the Google Doc you want the parser to read.
2. Click **Share** (top right).
3. Paste the service account email.
4. Set permission to **Viewer** (Editor isn't needed; the script only reads).
5. **Uncheck "Notify people"** — service accounts can't receive email, and Google will throw a confusing error otherwise.
6. **Share**. If Google warns "This email isn't associated with a Google account," click **Share anyway** — that's expected.

Repeat for any Doc you want the parser to read.

## 7. Get the Doc ID

The Doc ID is the long string in the URL between `/d/` and `/edit`:

```
https://docs.google.com/document/d/1AbCdEf_THIS_IS_THE_DOC_ID_xyz/edit
                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

## 8. Test the script

```bash
python parser.py \
  --doc-id <YOUR_DOC_ID> \
  --credentials path/to/newsletter-parser.json \
  --output test.html \
  --open-preview
```

If you see "ERROR: Google Docs API has not been used in project ... before or it is disabled," you enabled the API in a different project than the service account's. Click the link in the error, make sure you're in the right project, and click Enable.

If you see a 403 about permissions, the Doc isn't shared with the service account email. Re-do step 6.

## 9. Optional: environment variable

To avoid passing `--credentials` every run, set:

**Windows (PowerShell):**
```powershell
[Environment]::SetEnvironmentVariable("STO_NEWSLETTER_CREDS", "C:\Users\YOU\.credentials\newsletter-parser.json", "User")
```

**macOS/Linux (bash/zsh):**
```bash
echo 'export STO_NEWSLETTER_CREDS="$HOME/.credentials/newsletter-parser.json"' >> ~/.bashrc
```

(Restart your shell after setting.)

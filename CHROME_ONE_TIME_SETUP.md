# One-time Chrome setup on the emulator

To avoid the **"Welcome to Chrome"** / sign-in screen every time you open Chrome (manually or via Appium), do this **once** on your emulator. After that, Chrome will open directly to a normal tab until you clear Chrome data.

---

## Step 1: Open Chrome and dismiss the welcome screen

1. On the emulator, open **Chrome** (tap the Chrome icon).
2. You see **"Welcome to Chrome"** with:
   - **"Continue as &lt;your name&gt;"** (blue button)
   - **"Use without an account"** (link below)
3. Tap **"Use without an account"** (do **not** tap "Continue as …").

---

## Step 2: Set as default browser (if asked)

- If a dialog appears: **"Set Chrome as your default browser?"**
  - Tap **"Yes"** or **"Set as default"** (recommended),  
  - or **"No"** / **"Not now"** if you prefer.
- This step may not appear on all emulators.

---

## Step 3: Turn off sync / skip sign-in prompts (if shown)

- If you see **"Turn on sync?"** or **"Sign in to Chrome"**:
  - Tap **"No thanks"**, **"Not now"**, or **"Skip"**.
- If you see **"Save your passwords?"** or similar:
  - Choose **"Not now"** or **"Skip"** so you stay in a clean, non-signed-in state.

---

## Step 4: Confirm you’re past the welcome flow

- You should land on the **New Tab** page (empty or with a search bar), **not** on any sign-in or welcome screen.
- Close Chrome and open it again: it should go straight to the New Tab page.

---

## Summary

| Screen / prompt              | What to tap                          |
|-----------------------------|--------------------------------------|
| Welcome to Chrome           | **Use without an account**           |
| Set as default browser?     | **Yes** or **No** (your choice)      |
| Turn on sync? / Sign in?    | **No thanks** / **Not now** / **Skip** |
| Save passwords?             | **Not now** / **Skip**               |

After this one-time setup, both manual use and Appium can open Chrome without the welcome screen. If you **clear Chrome app data** (Settings → Apps → Chrome → Clear data) or use a new emulator snapshot, you’ll need to repeat these steps once.

---

## Why does the welcome screen keep coming back?

Even after tapping "Use without an account", the screen can still appear every time. Common reasons:

### 1. **Emulator / LDPlayer is not saving state**

When you close LDPlayer (or the emulator) or it restarts, it may be loading an **old snapshot** or running with **non-persistent storage**, so Chrome’s data (including “first run completed”) is lost.

**What to do:**

- After you finish the one-time setup (Steps 1–4 above), **save the emulator state** before closing:
  - **LDPlayer:** Use the built-in “Save snapshot” / “Snapshot” feature so the next boot uses this saved state.
  - Or avoid closing the emulator between runs; minimize it instead.
- Make sure you’re not starting from a “fresh” or “clean” snapshot that was created before the setup.

### 2. **Different Chrome “profile” when automation runs**

When you open Chrome **manually** (tap the icon), it uses the default profile and remembers “first run done.” When **Appium/Chromedriver** starts Chrome for a session, it can start Chrome in a **different way** (e.g. different intent or profile), so Chrome treats it as a **new** first run for that launch path.

**What to do:**

- Rely on the script’s **automatic dismiss** (`dismiss_chrome_welcome_if_present`): it taps “Use without an account” when the screen appears. You don’t need to avoid the screen manually for automation.
- Optionally try **Chrome flags** in `config.py` → `CHROME_EXTRA_ARGS` (e.g. `["--disable-fre", "--no-first-run"]`). On some setups this can cause “chrome not reachable”; if so, leave `CHROME_EXTRA_ARGS = []` and use the auto-dismiss.

**Why script vs manual?** When you tap the Chrome icon, Android uses the **default profile** (where you already tapped "Use without an account"). When the **script** starts Chrome, Appium/Chromedriver uses a **different launch context or profile** for automation, so Chrome treats that as a **new** first run. The one-time setup you did manually only applies to the default profile; the automation profile stays "first run not done", so the welcome screen shows every time you run the script.

### 3. **More than one emulator instance**

If you have **multiple LDPlayer (or other) instances**, each has its own Chrome data. Doing the one-time setup in **instance A** does not affect **instance B**.

**What to do:**

- Do the one-time setup in the **same** instance you use for automation (the one matching `APPIUM_UDID` in `config.py`).

### 4. **Chrome was updated**

After a **Chrome app update** on the device, the first-run screen sometimes appears again once.

**What to do:**

- Repeat the one-time setup (Steps 1–4) once after the update.

---

**Summary:** The most common cause on emulators is **(1) state not being saved**. Save an LDPlayer snapshot after completing the setup, and use that snapshot when you start the emulator so the welcome screen doesn’t keep coming back.

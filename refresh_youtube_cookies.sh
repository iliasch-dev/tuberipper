#!/usr/bin/env bash
# Refresh Netscape cookies for yt-dlp (tuberipper reads cookies/youtube_cookies.txt).
#
# Writes to cookies/youtube_cookies.txt only after a successful YouTube check (atomic replace).
#
# Usage:
#   ./refresh_youtube_cookies.sh
#   BROWSER=firefox ./refresh_youtube_cookies.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

YTDLP="${ROOT}/venv/bin/yt-dlp"
COOKIES_DIR="${ROOT}/cookies"
COOKIES_FILE="${COOKIES_DIR}/youtube_cookies.txt"
COOKIES_NEW="${COOKIES_DIR}/youtube_cookies.txt.new"
BROWSER="${BROWSER:-chrome}"
PROBE_URL="${PROBE_URL:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"

cleanup_new() {
  rm -f "$COOKIES_NEW"
}

die_ytdlp_missing() {
  cat >&2 <<EOF
================================================================================
FAILED: yt-dlp not found in the project venv
================================================================================
What to do before running this script again:

  1. cd to the tuberipper repo:  cd $ROOT
  2. Create/use the venv and install yt-dlp:
       python3 -m venv venv
       ./venv/bin/pip install -U yt-dlp
  3. Re-run:  ./refresh_youtube_cookies.sh

================================================================================
EOF
  exit 1
}

die_export_failed() {
  cat >&2 <<EOF
================================================================================
FAILED: Could not export cookies from browser ($BROWSER)
================================================================================
What to do before running this script again:

  1. Quit $BROWSER completely (all windows). On Linux, encrypted cookies need the
     profile to be unlocked and not in use — a running browser often blocks this.

  2. Open $BROWSER again, go to https://www.youtube.com and sign in. Play any
     video briefly to confirm the session works in the normal UI.

  3. If you saw errors about "secretstorage" or "could not decrypt cookie":
       cd $ROOT
       ./venv/bin/pip install SecretStorage
     Then quit the browser again and re-run this script.

  4. If Chrome keeps failing, try Firefox (must be logged into YouTube there):
       BROWSER=firefox ./refresh_youtube_cookies.sh

  5. Alternative (no browser export): use the Chrome extension "Get cookies.txt LOCALLY"
     while on youtube.com (signed in), export, then save the file as:
       $COOKIES_FILE
     Then run verification only by hand:
       $YTDLP --remote-components ejs:github --cookies "$COOKIES_FILE" --skip-download "$PROBE_URL"

================================================================================
EOF
  cleanup_new
  exit 1
}

die_no_cookies_decrypted() {
  cat >&2 <<EOF
================================================================================
FAILED: Browser reported 0 usable cookies (Chrome v11 / encryption / keyring)
================================================================================
Typical message from yt-dlp: "cannot decrypt v11 cookies: no key found" or
"Extracted 0 cookies ... (N could not be decrypted)".

Your session is NOT in the exported file. tuberipper would still hit YouTube
"sign in / bot" errors even though a probe video might look OK.

What to do before running this script again:

  1. Run this script from a normal desktop login on this machine (not only SSH),
     with your graphical session unlocked so the OS keyring (GNOME Keyring /
     KWallet) is available. Chrome ties cookie decryption to that keyring.

  2. Install Python keyring support in this venv (often required on Linux):
       cd $ROOT
       ./venv/bin/pip install SecretStorage

  3. Fully quit Chrome, then run this script again. If it still shows 0 cookies,
     try Firefox instead (log into YouTube there first):
       BROWSER=firefox ./refresh_youtube_cookies.sh

  4. Easiest reliable path: install "Get cookies.txt LOCALLY" in Chrome, open
     youtube.com while signed in, export cookies, save manually as:
       $COOKIES_FILE
     Then install Deno, and verify:
       deno --version
       $YTDLP --remote-components ejs:github --cookies "$COOKIES_FILE" --skip-download "$PROBE_URL"

================================================================================
EOF
  cleanup_new
  exit 1
}

die_no_youtube_rows() {
  cat >&2 <<EOF
================================================================================
FAILED: Cookie file has no youtube.com entries after export
================================================================================
What to do before running this script again:

  1. Sign in to https://www.youtube.com in $BROWSER, then quit the browser and
     re-run this script.

  2. If you use Chrome on Linux and see decrypt warnings, read the steps in the
     "0 usable cookies / v11" failure message (keyring, SecretStorage, Firefox,
     or extension export).

================================================================================
EOF
  cleanup_new
  exit 1
}

die_empty_file() {
  cat >&2 <<EOF
================================================================================
FAILED: Cookie file is missing or empty after export
================================================================================
What to do before running this script again:

  1. Repeat the same steps as "export failed": sign in on YouTube in $BROWSER,
     quit the browser fully, re-run this script.

  2. If it keeps writing an empty file, use the extension method in the export-failed
     message and place a non-empty Netscape cookies file at:
       $COOKIES_FILE

================================================================================
EOF
  cleanup_new
  exit 1
}

die_deno_missing() {
  cat >&2 <<EOF
================================================================================
FAILED: Deno is not on PATH (required for yt-dlp YouTube JS / EJS)
================================================================================
You probably saw: "No supported JavaScript runtime could be found".

What to do before running this script again:

  1. Install Deno and put it on your PATH, then confirm in the SAME terminal:
       deno --version

     Common install:
       curl -fsSL https://deno.land/install.sh | sh
     Then add Deno's bin directory to PATH (the installer prints the exact line).

  2. Re-run:  ./refresh_youtube_cookies.sh

  3. If you run tuberipper from cron or systemd, ensure PATH in that environment
     includes Deno (or set PATH inside the unit/crontab).

================================================================================
EOF
  cleanup_new
  exit 1
}

die_verify_failed() {
  cat >&2 <<EOF
================================================================================
FAILED: YouTube did not accept the saved cookie file (verification step)
================================================================================
The file was NOT installed as $COOKIES_FILE (your previous cookies, if any, are unchanged).

What to do before running this script again:

  1. Sign in and refresh the session in the browser
     - Open $BROWSER, go to https://www.youtube.com
     - If Google asks you to sign in or verify, complete that until you can watch
       a video normally.

  2. Quit the browser completely, then run this script again so export sees a fresh,
     valid profile.

  3. Confirm Deno works:  deno --version

  4. Upgrade yt-dlp in this project:
       cd $ROOT
       ./venv/bin/pip install -U yt-dlp

  5. Read the yt-dlp error output printed above — if it says "Sign in" or "bot",
     the browser session was still not good enough; repeat steps 1–2.

  6. If you are on a VPN or datacenter IP, try from your home/residential network
     if possible (YouTube sometimes blocks scripted access more aggressively).

================================================================================
EOF
  cleanup_new
  exit 2
}

# --- main ---

if [[ ! -x "$YTDLP" ]]; then
  die_ytdlp_missing
fi

if ! command -v deno >/dev/null 2>&1; then
  die_deno_missing
fi

mkdir -p "$COOKIES_DIR"
cleanup_new

export_log="$(mktemp)"
trap 'rm -f "$export_log"' EXIT

echo "Exporting cookies from browser: $BROWSER -> $COOKIES_NEW (temporary)"
echo "Tip: quit $BROWSER first if the export fails or complains about a locked profile."
set +e
"$YTDLP" --remote-components ejs:github \
  --cookies-from-browser "$BROWSER" \
  --cookies "$COOKIES_NEW" \
  --skip-download \
  --no-progress \
  "$PROBE_URL" >"$export_log" 2>&1
export_rc=$?
set -e
cat "$export_log"
if [[ "$export_rc" -ne 0 ]]; then
  die_export_failed
fi

if grep -qE 'Extracted 0 cookies from' "$export_log"; then
  die_no_cookies_decrypted
fi

if [[ ! -s "$COOKIES_NEW" ]]; then
  die_empty_file
fi

if ! grep -qF '.youtube.com' "$COOKIES_NEW"; then
  die_no_youtube_rows
fi

echo ""
echo "Verifying cookies (yt-dlp using only the file under cookies/, no browser)..."
set +e
"$YTDLP" --remote-components ejs:github \
  --cookies "$COOKIES_NEW" \
  --skip-download \
  --no-progress \
  "$PROBE_URL" 2>&1
verify_rc=$?
set -e
if [[ "$verify_rc" -ne 0 ]]; then
  die_verify_failed
fi

mv -f "$COOKIES_NEW" "$COOKIES_FILE"
trap - EXIT
rm -f "$export_log"

echo ""
echo "Done. Cookies installed at: $COOKIES_FILE"

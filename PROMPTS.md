# Vibe Coding Session — Prompts Used

This entire project was built through conversation with Claude. No code was written by hand. The following is the complete prompt sequence. Feed them to Claude in order to recreate the project from scratch.

---

**1. Kick it off**

> I'll help you convert parental ratings in your Jellyfin library to Australian ratings. Let me first check if you've uploaded any files, and understand what we're working with.
> Could you tell me a bit more about your setup?

Describe your Jellyfin server, how you authenticate (API key or username/password), and what you want the tool to do. Claude will generate the initial script from that description.

---

**2. Colour the stat line**

> need to update this script so that the Non-AU/Empty: 0 is green if none need to be updated.

---

**3. Trim the rating picker**

> and remove [X 18+, E, RC, P, C, AV 15+] from the rating picker menu

---

**4. Make it orange when non-zero**

> can it be orange when its more than 0

---

**5. Request an improvements review**

> are there any improvements, both visually and from a menu navigation perspective you could suggest

Claude identified 12 issues:

*Navigation*
1. Rating Breakdown exits to type selector after viewing items instead of back to the ratings list
2. Inherit Series is single-shot — fixing one series ejects you to the main menu
3. Search is single-shot — same problem
4. Silent failure on `n`/`p` at page boundaries
5. No exit confirmation
6. Inherit Series caps display at 30 with no way to select beyond that

*Visual*
7. No colour on status tags in Rating Breakdown
8. `✓ Updated` / `✗ Failed` messages have no colour
9. Error count in bulk done summary has no colour
10. Items in the view list don't show their current rating
11. Command help block reprinted every page
12. Header never shows who you're logged in as

---

**6. Implement all suggestions**

> yes implement all

---

**7. Design test cases**

> design a number of test cases for this script

---

**8. Add credential storage**

> is there a way to store the credentials so it remembers next time?

Claude offered three options (config file, OS keyring, both with fallback). Config file was chosen.

---

**9. Add quit-from-anywhere**

> also there should be a way to quit the script from any screen rather than having to navigate back to the main menu.

---

**10. Fix bad-password exit**

> also if you enter wrong password - script exits doesnt allow you to try again

---

**11. Review and expand test cases**

> so review the test cases add any missing and test

Claude identified six gaps: credential store (zero tests), Canadian/Brazilian ratings, `authenticate_with_api_key`, `authenticate_with_password`, `get_all_items` pagination, `_print_done` output, and additional `_do_update` failure modes.

---

**12. Add host to the setup flow**

> as apart of setup need to be able to add the jellyfin host (alongside creds)
> the logged on user line needs to be on the same line as the title

---

**13. Remove the hardcoded URL**

> jellyfin.homenook.xyz has been hardcoded

---

**14. Write the README**

> ok i need a readme.md emphasising that this was vibe coded. include test cases and summary of prompts used to recreate

---

**15. Split the docs**

> can we break up Readme so test cases and prompts are in separate files but linked to readme

---

← Back to [README.md](README.md)

# Meowth (with Huntr Integration by Doonce)
A Discord helper bot for Pokemon Go communities.

Meowth is a Discord bot written in Python 3.5 using version 0.16.12 of the discord.py library.

This Huntr integrating fork is based on the original Meowth, but is not affiliated or supported by the official development team. Please to not ask for support of this ToS-violating version in the official support channels as it will not be welcomed.

## Meowth 2.0 is here!

A list of current features:

1. User-driven (not automated) wild spawn and raid reporting.
2. Role management for each Pokemon species (Discord limits a server to 250 roles, however) that allows each user to opt-in only for the Pokemon they want. These roles are mentioned when spawns or raids are reported.
3. Raid reporting: Report either !raidegg, !raid or !exraid on the server to have meowth create channels to organise in. Certain commands can be used within raid channels, such as updating your stauts with !interested, !coming and !here. Users can easily determine the status of involved members with the !list command. Meowth also queries Google Maps to get a guess of the raid location (no access to the game means no list of gyms), or you can paste a maps link in the channel after creation to update it to exact coordinates.
4. Optional team management and new member welcome functions.

## Directions for installing and running the bot on your server (with Huntr Integration):


1. Install Python 3.5 and ensure PIP is also installed with it.
https://www.python.org/downloads/release/python-350/

2. Install the packages needed to run meowth by running install.py:

Linux:
```bash
python3 install.py
```
Windows:
```bash
py install.py
```
Tesseract-OCR has to be installed with a standard binary installer on Windows.
Get the installer [HERE](https://github.com/tesseract-ocr/tesseract/wiki/Downloads)

3. Make sure the Tesseract-OCR install folder and your python install folder are added to your system environment PATH variable.

4. Download the files in this repository. The source code is in meowth.py and bot config is in config.json.

5. Go to https://discordapp.com/developers/applications/me#top and create a new app.

6. Name it and upload the avatar of your choice.

7. Create a bot user for your app and reveal the bot token to copy it.

8. Copy config_blank.json and rename to config.json.

9. Open config.json in a text editor (a good one to use is Notepad++) and paste the bot token into the value for "bot_token", replacing the "yourtoken" string.

10. Replace the "master" value in config.json with your user ID from discord.

11. Go back to your Discord application page and copy the Client ID.

12. Go to the following link, replacing <CLIENT_ID> with the Client ID you copied.
`https://discordapp.com/oauth2/authorize?client_id=<CLIENT_ID>&scope=bot&permissions=268822608`

13. Select the server you want to add Meowth to and complete the prompts. If you get to an empty screen and didn't get to see the Google new reCaptcha tickbox, disable your adblocker.

14. Make sure you have git installed and update your discord.py file to latest version using:

Linux:
```bash
python3 -m pip install -U git+https://github.com/Rapptz/discord.py@rewrite
```
Windows:
```bash
py -m pip install -U git+https://github.com/Rapptz/discord.py@rewrite
```

15. Run the launcher from the command prompt or terminal window:

Linux:
```bash
python3 launcher.py -s
```
Windows:
```bash
py launcher.py -s
```

If successful, it should show "Meowth! That's right!".

16. The bot should have sent you DM in Discord. Add the team roles: mystic, instinct and valor. Ensure they're below the bot role in the server role hierarchy.

17. Simply type !configure in your server to start the configuration process.

### Launcher Reference:
Arguments:
```
  --help, -h          Show the help message
  --start, -s         Starts Meowth
  --auto-restart, -r  Auto-Restarts Meowth in case of a crash.
  --debug, -d         Prevents output being sent to Discord DM, as restarting
                      could occur often.
```

Launch Meowth normally:
```bash
python3 launcher.py -s
```

Launch Meowth in debug mode if working on code changes:
```bash
python3 launcher.py -s -d
```

Launch Meowth with Auto-Restart:
```bash
python3 launcher.py -s -r
```

## Directions for using Meowth:
Note: Avoid punctuation inside commands.

Arguments within \< \> are required.<br/>
Arguments within \[ \] are optional.<br/>
pkmn = Pokemon

### General Commands:

| Commands | Requirements  | Description |
| -------- |:-------------:| ------------|
| **!help** \[command\] | - | Shows bot/command help, with descriptions. |
| **!about** | - | Shows info about Meowth. |
| **!team** \<team\> | - | Let's users set their team role. |
| **!save**  | *Owner Only* | Saves the save data to file. |
| **!exit**  | *Owner Only* | Saves the save data to file and shutdown Meowth. |
| **!restart**  | *Owner Only* | Saves the save data to file and restarts Meowth. |
| **!announce** \[msg\] | *Owner Only* | Sends announcement message to server owners. |
| **!welcome** \[@member\] | *Owner Only* | Sends the welcome message to either user or mentioned member. |
| **!outputlog**  | *Server Manager Only* | Uploads the log file to hastebin and replies with the link. |

### Pokemon Notification Commands:

| Commands | Requirements  | Description |
| -------- |:-------------:| ------------|
| **!want** \<pkmn\> | - | Adds a Pokemon to your notification roles. |
| **!unwant** \<pkmn\> | - | Removes a Pokemon from your notification roles. |
| **!unwant all**  | - | Removes all Pokemon from your notification roles. |
| **!wild** \<pkmn\> \<location\> | *Region Channel* | Reports a wild pokemon, notifying people who want it. |


### Raid Commands:

| Commands | Requirements  | Description |
| -------- |:-------------:| ------------|
| **!raid** \<pkmn\> \<place\> \[timer\] | *Region Channel* | Creates an open raid channel. |
| **!exraid** \<pkmn\> \<place\> | *Region Channel* | Creates an exraid channel. |
| **!invite**  | *Region Channel* | Check attached pass for entry to exraids. |
| **!raidegg** \<level\> \<place\> \[timer\] | *Region Channel* | Creates a raid egg channel. |
| **!raid** \<pkmn\> | *Raid Egg Channel* | Converts raid egg to an open raid. |
| **!timer** | *Raid Channel* | Shows the expiry time for the raid. |
| **!timerset** \<timer\> | *Raid Channel* | Set the expiry time for the raid. |
| **!location** | *Raid Channel* | Shows the raid location. |
| **!location new** \<place/map\> | *Raid Channel* | Sets the raid location. |
| **!interested** \[number\] | *Raid Channel* | Sets your status for the raid to 'interested'. |
| **!coming** \[number\] | *Raid Channel* | Sets your status for the raid to 'coming'. |
| **!here** \[number\] | *Raid Channel* | Sets your status for the raid to 'here'. |
| **!starting** | *Raid Channel* | Clears all members 'here', announce raid start. |
| **!cancel**  | *Raid Channel* | Cancel your status. |
| **!clearstatus**  | *Server Manager<br/>Raid Channel* | Cancel everyone's status. |
| **!list** | *Region Channel* | Lists all raids from that region channel. |
| **!list**  | *Raid Channel* | Lists all member status' for the raid. |
| **!list interested** | *Raid Channel* | Lists 'interested' members for the raid. |
| **!list coming**  | *Raid Channel* | Lists 'coming' members for the raid. |
| **!list here** | *Raid Channel* | Lists 'here' members for the raid. |
| **!duplicate** | *Raid Channel* | Reports the raid as a duplicate channel. |

## General notes on Meowth:

Meowth relies completely on users for reports. Meowth was designed as an alternative to Discord bots that use scanners and other illegitimate sources of information about Pokemon Go. As a result, Meowth works only as well as the users who use it. As there are 10+ ways of interacting with Meowth, there can be a bit of a rough learning period, but it quickly becomes worth it.

## Known issues:

Compatibility with Python 3.6 on Mac OS X requires running "Install Certificates.command" in the Python 3.6 folder.

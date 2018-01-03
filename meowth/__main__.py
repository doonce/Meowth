import os
import sys
import tempfile
import asyncio
import gettext
import re
import pickle
import json
import time
import datetime
from dateutil.relativedelta import relativedelta
from dateutil import tz
import copy
from time import strftime
from logs import init_loggers
import discord
from discord.ext import commands
import pkmn_match
from PIL import Image
from PIL import ImageFilter
from PIL import ImageEnhance
import pytesseract
import requests
from io import BytesIO
import checks
import hastebin
from operator import itemgetter
from errors import custom_error_handling

tessdata_dir_config = "--tessdata-dir 'C:\\Program Files (x86)\\Tesseract-OCR\\tessdata' "
xtraconfig = "-l eng -c tessedit_char_blacklist=&|=+%#^*[]{};<> -psm 6"

if os.name == 'nt':
    tesseract_config = tessdata_dir_config + xtraconfig
else:
    tesseract_config = xtraconfig

logger = init_loggers()

def _get_prefix(bot,message):
    server = message.server
    try:
        set_prefix = bot.server_dict[server.id]["prefix"]
    except (KeyError, AttributeError):
        set_prefix = None
    default_prefix = bot.config["default_prefix"]
    return set_prefix or default_prefix

Meowth = commands.Bot(command_prefix=_get_prefix)
custom_error_handling(Meowth,logger)

try:
    with open(os.path.join('data', 'serverdict'), "rb") as fd:
        Meowth.server_dict = pickle.load(fd)
    logger.info("Serverdict Loaded Successfully")
except OSError:
    logger.info("Serverdict Not Found - Looking for Backup")
    try:
        with open(os.path.join('data', 'serverdict_backup'), "rb") as fd:
            Meowth.server_dict = pickle.load(fd)
        logger.info("Serverdict Backup Loaded Successfully")
    except OSError:
        logger.info("Serverdict Backup Not Found - Creating New Serverdict")
        Meowth.server_dict = {}
        with open(os.path.join('data', 'serverdict'), "wb") as fd:
            pickle.dump(Meowth.server_dict, fd, -1)
        logger.info("Serverdict Created")

server_dict = Meowth.server_dict

config = {}
pkmn_info = {}
type_chart = {}
type_list = []
raid_info = {}
active_raids = []

# Append path of this script to the path of
# config files which we're loading.
# Assumes that config files will always live in the same directory.
script_path = os.path.dirname(os.path.realpath(__file__))

def load_config():
    global config
    global pkmn_info
    global type_chart
    global type_list
    global raid_info

    # Load configuration
    with open("config.json", "r") as fd:
        config = json.load(fd)

    # Set up message catalog access
    language = gettext.translation('meowth', localedir='locale', languages=[config['bot-language']])
    language.install()
    pokemon_language = [config['pokemon-language']]
    pokemon_path_source = os.path.join('locale', '{0}', 'pkmn.json').format(config['pokemon-language'])

    # Load Pokemon list and raid info
    with open(pokemon_path_source, "r") as fd:
        pkmn_info = json.load(fd)
    with open(os.path.join('data', 'raid_info.json'), "r") as fd:
        raid_info = json.load(fd)

    # Load type information
    with open(os.path.join('data', 'type_chart.json'), "r") as fd:
        type_chart = json.load(fd)
    with open(os.path.join('data', 'type_list.json'), "r") as fd:
        type_list = json.load(fd)

    # Set spelling dictionary to our list of Pokemon
    pkmn_match.set_list(pkmn_info['pokemon_list'])

load_config()

Meowth.config = config

"""

======================

Helper functions

======================

"""
def _set_prefix(bot,server,prefix):
    bot.server_dict[server.id]["prefix"] = prefix

# Given a Pokemon name, return a list of its
# weaknesses as defined in the type chart
def get_type(server, pkmn_number):
    pkmn_number = int(pkmn_number)-1
    types = type_list[pkmn_number]
    ret = []
    for type in types:
        ret.append(parse_emoji(server, config['type_id_dict'][type.lower()]))
    return ret

def get_name(pkmn_number):
    pkmn_number = int(pkmn_number)-1
    name = pkmn_info['pokemon_list'][pkmn_number].capitalize()
    return name

def get_number(pkm_name):
    number = pkmn_info['pokemon_list'].index(pkm_name) + 1
    return number

def get_level(pkmn):
    if str(pkmn).isdigit():
        pkmn_number = pkmn
    elif not str(pkmn).isdigit():
        pkmn_number = get_number(pkmn)
    for level in raid_info["raid_eggs"]:
        for pokemon in raid_info["raid_eggs"][level]["pokemon"]:
            if pokemon == pkmn_number:
                return level

def get_raidlist():
    raidlist = []
    for level in raid_info["raid_eggs"]:
        for pokemon in raid_info["raid_eggs"][level]["pokemon"]:
            raidlist.append(pokemon)
            raidlist.append(get_name(pokemon).lower())
    return raidlist

# Given a Pokemon name, return a list of its
# weaknesses as defined in the type chart
def get_weaknesses(species):
    # Get the Pokemon's number
    number = pkmn_info['pokemon_list'].index(species)
    # Look up its type
    pk_type = type_list[number]

    # Calculate sum of its weaknesses
    # and resistances.
    # -2 == immune
    # -1 == NVE
    #  0 == neutral
    #  1 == SE
    #  2 == double SE
    type_eff = {}
    for type in pk_type:
        for atk_type in type_chart[type]:
            if atk_type not in type_eff:
                type_eff[atk_type] = 0
            type_eff[atk_type] += type_chart[type][atk_type]

    # Summarize into a list of weaknesses,
    # sorting double weaknesses to the front and marking them with 'x2'.
    ret = []
    for type, effectiveness in sorted(type_eff.items(), key=lambda x: x[1], reverse=True):
        if effectiveness == 1:
            ret.append(type.lower())
        elif effectiveness == 2:
            ret.append(type.lower() + "x2")

    return ret


# Given a list of weaknesses, return a
# space-separated string of their type IDs,
# as defined in the type_id_dict
def weakness_to_str(server, weak_list):
    ret = ""
    for weakness in weak_list:
        # Handle an "x2" postfix defining a double weakness
        x2 = ""
        if weakness[-2:] == "x2":
            weakness = weakness[:-2]
            x2 = "x2"

        # Append to string
        ret += parse_emoji(server, config['type_id_dict'][weakness]) + x2 + " "

    return ret


# Convert an arbitrary string into something which
# is acceptable as a Discord channel name.
def sanitize_channel_name(name):
    # Remove all characters other than alphanumerics,
    # dashes, underscores, and spaces
    ret = re.sub(r"[^a-zA-Z0-9 _\-]", "", name)
    # Replace spaces with dashes
    ret = ret.replace(" ", "-")
    return ret

# Given a string, if it fits the pattern :emoji name:,
# and <emoji_name> is in the server's emoji list, then
# return the string <:emoji name:emoji id>. Otherwise,
# just return the string unmodified.
def parse_emoji(server, emoji_string):
    if emoji_string[0] == ':' and emoji_string[-1] == ':':
        emoji = discord.utils.get(server.emojis, name=emoji_string.strip(':'))
        if emoji:
            emoji_string = "<:{0}:{1}>".format(emoji.name, emoji.id)
    return emoji_string

def print_emoji_name(server, emoji_string):
    # By default, just print the emoji_string
    ret = "`" + emoji_string + "`"

    emoji = parse_emoji(server, emoji_string)
    # If the string was transformed by the parse_emoji
    # call, then it really was an emoji and we should
    # add the raw string so people know what to write.
    if emoji != emoji_string:
        ret = emoji + " (`" + emoji_string + "`)"

    return ret

# Given an arbitrary string, create a Google Maps
# query using the configured hints
def create_gmaps_query(details, channel):
    details_list = details.split()
    loc_list = server_dict[channel.server.id]['city_channels'][channel.name].split()
    return "https://www.google.com/maps/search/?api=1&query={0}+{1}".format('+'.join(details_list),'+'.join(loc_list))

# Given a User, check that it is Meowth's master
def check_master(user):
    return str(user) == config['master']

def check_server_owner(user, server):
    return str(user) == str(server.owner)

# Given a violating message, raise an exception
# reporting unauthorized use of admin commands
def raise_admin_violation(message):
    raise Exception(_("Received admin command {command} from unauthorized user, {user}!").format(command=message.content, user=message.author))

def spellcheck(word):
    suggestion = pkmn_match.get_pkmn(re.sub(r"[^A-Za-z0-9 ]+", '', word))
    # If we have a spellcheck suggestion
    if suggestion != word:
        result = pkmn_info['pokemon_list'][suggestion]
        return _("Sorry, I don't know of any \"{entered_word}\". Did you mean \"{corrected_word}\"?").format(entered_word=word, corrected_word=result.title())
    else:
        return _("Sorry! I haven't heard of a \"{entered_word}\" Pokemon.").format(entered_word=word)

async def expiry_check(channel):
    logger.info("Expiry_Check - "+channel.name)
    server = channel.server
    global active_raids
    if channel not in active_raids:
        active_raids.append(channel)
        logger.info("Expire_Channel - Channel Added To Watchlist - "+channel.name)
        await asyncio.sleep(0.5) #wait for assume
        while True:
            try:
                if server_dict[server.id]['raidchannel_dict'][channel.id]['active'] is True:
                    if server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] is not None:
                        if server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] <= time.time():
                            if server_dict[server.id]['raidchannel_dict'][channel.id]['type'] == 'egg':
                                pokemon = server_dict[server.id]['raidchannel_dict'][channel.id]['pokemon']
                                if pokemon:
                                    logger.info("Expire_Channel - Egg Auto Hatched - "+channel.name)
                                    try:
                                        active_raids.remove(channel)
                                    except ValueError:
                                        logger.info("Expire_Channel - Channel Removal From Active Raid Failed - Not in List - "+channel.name)
                                    await _eggtoraid(pokemon.lower(), channel, huntr=False)
                                    break
                            event_loop.create_task(expire_channel(channel))
                            try:
                                active_raids.remove(channel)
                            except ValueError:
                                logger.info("Expire_Channel - Channel Removal From Active Raid Failed - Not in List - "+channel.name)
                            logger.info("Expire_Channel - Channel Expired And Removed From Watchlist - "+channel.name)
                            break
            except KeyError:
                pass

            await asyncio.sleep(30)
            continue

async def expire_channel(channel):
    server = channel.server
    alreadyexpired = False
    logger.info("Expire_Channel - "+channel.name)
    # If the channel exists, get ready to delete it.
    # Otherwise, just clean up the dict since someone
    # else deleted the actual channel at some point.

    channel_exists = Meowth.get_channel(channel.id)
    if channel_exists is None and Meowth.is_logged_in and not Meowth.is_closed:
        try:
            del server_dict[channel.server.id]['raidchannel_dict'][channel.id]
        except KeyError:
            pass
        return
    else:
        dupechannel = False
        gymhuntrdupe = False
        if server_dict[server.id]['raidchannel_dict'][channel.id]['active'] == False:
            alreadyexpired = True
        else:
            server_dict[server.id]['raidchannel_dict'][channel.id]['active'] = False
        logger.info("Expire_Channel - Channel Expired - "+channel.name)
        try:
            testvar = server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate']
        except KeyError:
            server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate'] = 0
        if server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate'] >= 3:
            if server_dict[server.id]['raidchannel_dict'][channel.id]['gymhuntrgps'] is not False:
                gymhuntrexp = server_dict[server.id]['raidchannel_dict'][channel.id]['exp']
                gymhuntrdupe = True
            dupechannel = True
            server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate'] = 0
            server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] = time.time()
            if not alreadyexpired:
                await Meowth.send_message(channel, _("""This channel has been successfully reported as a duplicate and will be deleted in 1 minute. Check the channel list for the other raid channel to coordinate in!
If this was in error, reset the raid with **!timerset**"""))
            delete_time = server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] + (1 * 60) - time.time()
        elif server_dict[server.id]['raidchannel_dict'][channel.id]['type'] == 'egg':
            if not alreadyexpired:
                maybe_list = []
                trainer_dict = copy.deepcopy(server_dict[channel.server.id]['raidchannel_dict'][channel.id]['trainer_dict'])
                for trainer in trainer_dict.keys():
                    if trainer_dict[trainer]['status']=='maybe':
                        user = channel.server.get_member(trainer)
                        maybe_list.append(user.mention)
                await Meowth.send_message(channel, _("""**This egg has hatched!**\n\n...or the time has just expired. Trainers {trainer_list}: Update the raid to the pokemon that hatched using **!raid <pokemon>** or reset the hatch timer with **!timerset**. This channel will be deactivated until I get an update and I'll delete it in 15 minutes if I don't hear anything.""").format(trainer_list=", ".join(maybe_list)))
            delete_time = server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] + (15 * 60) - time.time()
            expiremsg = _("**This level {level} raid egg has expired!**").format(level=server_dict[channel.server.id]['raidchannel_dict'][channel.id]['egglevel'])
        else:
            if not alreadyexpired:
                await Meowth.send_message(channel, _("""This channel timer has expired! The channel has been deactivated and will be deleted in 5 minutes.
To reactivate the channel, use **!timerset** to set the timer again."""))
            delete_time = server_dict[server.id]['raidchannel_dict'][channel.id]['exp'] + (5 * 60) - time.time()
            expiremsg = _("**This {pokemon} raid has expired!**").format(pokemon=server_dict[channel.server.id]['raidchannel_dict'][channel.id]['pokemon'].capitalize())
        await asyncio.sleep(delete_time)
        # If the channel has already been deleted from the dict, someone
        # else got to it before us, so don't do anything.
        # Also, if the channel got reactivated, don't do anything either.
        try:
            if server_dict[channel.server.id]['raidchannel_dict'][channel.id]['active'] == False and Meowth.is_logged_in and not Meowth.is_closed:
                if dupechannel:
                    report_channel = Meowth.get_channel(server_dict[server.id]['raidchannel_dict'][channel.id]['reportcity'])
                    reportmsg = await Meowth.get_message(report_channel, server_dict[channel.server.id]['raidchannel_dict'][channel.id]['raidreport'])
                    try:
                        await Meowth.delete_message(reportmsg)
                    except:
                        pass
                else:
                    report_channel = Meowth.get_channel(server_dict[server.id]['raidchannel_dict'][channel.id]['reportcity'])
                    reportmsg = await Meowth.get_message(report_channel, server_dict[channel.server.id]['raidchannel_dict'][channel.id]['raidreport'])
                    try:
                        await Meowth.edit_message(reportmsg, embed=discord.Embed(description=expiremsg,colour=channel.server.me.colour))
                    except:
                        pass
                try:
                    if gymhuntrdupe == False:
                        del server_dict[channel.server.id]['raidchannel_dict'][channel.id]
                except KeyError:
                    pass
                    #channel doesn't exist anymore in serverdict
                channel_exists = Meowth.get_channel(channel.id)
                if channel_exists is None:
                    return
                elif gymhuntrdupe == False:
                    await Meowth.delete_channel(channel_exists)
                    logger.info("Expire_Channel - Channel Deleted - "+channel.name)
                elif gymhuntrdupe == True:
                    for overwrite in channel.overwrites:
                        await Meowth.edit_channel_permissions(channel, channel.server.default_role, overwrite=discord.PermissionOverwrite(read_messages=False))
                        if server.me.top_role.name not in overwrite[0].name and server.me.name not in overwrite[0].name:
                            await Meowth.delete_channel_permissions(channel, overwrite[0])
                    await Meowth.send_message(channel, "-----------------------------------------------\n**The channel has been removed from view for everybody but Meowth and server owner to protect from future GymHuntr duplicates. It will be removed on its own, please do not remove it. Just ignore what happens in this channel.**\n-----------------------------------------------")
                    deltime = ((gymhuntrexp - time.time()) / 60) + 10
                    await _timerset(channel, deltime)
        except:
            pass


async def channel_cleanup(loop=True):
    while Meowth.is_logged_in and not Meowth.is_closed:
        global active_raids
        serverdict_chtemp = copy.deepcopy(server_dict)
        logger.info("Channel_Cleanup ------ BEGIN ------")

        #for every server in save data
        for serverid in serverdict_chtemp.keys():
            server = Meowth.get_server(serverid)
            log_str = "Channel_Cleanup - Server: "+serverid
            log_str = log_str + " - CHECKING FOR SERVER"
            if server is None:
                logger.info(log_str+": NOT FOUND")
                continue
            logger.info(log_str+" ("+server.name+")  - BEGIN CHECKING SERVER")

            #clear channel lists
            dict_channel_delete = []
            discord_channel_delete =[]

            #check every raid channel data for each server
            for channelid in serverdict_chtemp[serverid]['raidchannel_dict']:
                channel = Meowth.get_channel(channelid)
                log_str = "Channel_Cleanup - Server: "+server.name
                log_str = log_str+": Channel:"+channelid
                logger.info(log_str+" - CHECKING")

                channelmatch = Meowth.get_channel(channelid)

                if channelmatch is None:
                    #list channel for deletion from save data
                    dict_channel_delete.append(channelid)
                    logger.info(log_str+" - DOESN'T EXIST IN DISCORD")
                #otherwise, if meowth can still see the channel in discord
                else:
                    logger.info(log_str+" ("+channel.name+") - EXISTS IN DISCORD")
                    #if the channel save data shows it's not an active raid
                    if serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['active'] == False:

                        if serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['type'] == 'egg':

                            #and if it has been expired for longer than 15 minutes already
                            if serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['exp'] < (time.time() - (15 * 60)):

                                #list the channel to be removed from save data
                                dict_channel_delete.append(channelid)

                                #and list the channel to be deleted in discord
                                discord_channel_delete.append(channel)

                                logger.info(log_str+" - 15+ MIN EXPIRY NONACTIVE EGG")
                                continue

                        else:

                            #and if it has been expired for longer than 5 minutes already
                            if serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['exp'] < (time.time() - (5 * 60)):

                                #list the channel to be removed from save data
                                dict_channel_delete.append(channelid)

                                #and list the channel to be deleted in discord
                                discord_channel_delete.append(channel)

                                logger.info(log_str+" - 5+ MIN EXPIRY NONACTIVE RAID")
                                continue

                        event_loop.create_task(expire_channel(channel))
                        logger.info(log_str+" - = RECENTLY EXPIRED NONACTIVE RAID")
                        continue


                    #if the channel save data shows it as an active raid still
                    elif serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['active'] == True:

                        #if it's an exraid
                        if serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['type'] == 'exraid':

                            logger.info(log_str+" - EXRAID")
                            continue

                        #and if it has been expired for longer than 5 minutes already
                        elif serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['exp'] < (time.time() - (5 * 60)):

                            #list the channel to be removed from save data
                            dict_channel_delete.append(channelid)

                            #and list the channel to be deleted in discord
                            discord_channel_delete.append(channel)

                            logger.info(log_str+" - 5+ MIN EXPIRY ACTIVE")
                            continue

                        #or if the expiry time for the channel has already passed within 5 minutes
                        elif serverdict_chtemp[serverid]['raidchannel_dict'][channelid]['exp'] <= time.time():

                            #list the channel to be sent to the channel expiry function
                            event_loop.create_task(expire_channel(channel))

                            logger.info(log_str+" - RECENTLY EXPIRED")
                            continue

                        else:
                            #if channel is still active, make sure it's expiry is being monitored
                            if channel not in active_raids:
                                event_loop.create_task(expiry_check(channel))
                                logger.info(log_str+" - MISSING FROM EXPIRY CHECK")
                                continue

            #for every channel listed to have save data deleted
            for c in dict_channel_delete:
                try:
                    #attempt to delete the channel from save data
                    del server_dict[serverid]['raidchannel_dict'][c]
                    logger.info("Channel_Cleanup - Channel Savedata Cleared - " + c)
                except KeyError:
                    pass

            #for every channel listed to have the discord channel deleted
            for c in discord_channel_delete:
                try:
                    #delete channel from discord
                    await Meowth.delete_channel(c)
                    logger.info("Channel_Cleanup - Channel Deleted - " + c.name)
                except:
                    logger.info("Channel_Cleanup - Channel Deletion Failure - " + c.name)
                    pass

        #save server_dict changes after cleanup
        logger.info("Channel_Cleanup - SAVING CHANGES")
        try:
            await _save()
        except Exception as err:
            logger.info("Channel_Cleanup - SAVING FAILED" + err)
        logger.info("Channel_Cleanup ------ END ------")

        await asyncio.sleep(600)#600 default
        continue

async def server_cleanup(loop=True):
    while Meowth.is_logged_in and not Meowth.is_closed:
        serverdict_srvtemp = copy.deepcopy(server_dict)
        logger.info("Server_Cleanup ------ BEGIN ------")

        serverdict_srvtemp = server_dict
        dict_server_list = []
        bot_server_list = []
        dict_server_delete = []

        for serverid in serverdict_srvtemp.keys():
            dict_server_list.append(serverid)
        for server in Meowth.servers:
            bot_server_list.append(server.id)
        server_diff = set(dict_server_list) - set(bot_server_list)
        for s in server_diff:
            dict_server_delete.append(s)

        for s in dict_server_delete:
            try:
                del server_dict[s]
                logger.info("Server_Cleanup - Cleared "+s+" from save data")
            except KeyError:
                pass

        logger.info("Server_Cleanup - SAVING CHANGES")
        try:
            await _save()
        except Exception as err:
            logger.info("Server_Cleanup - SAVING FAILED" + err)
        logger.info("Server_Cleanup ------ END ------")
        await asyncio.sleep(7200)#7200 default
        continue

async def _print(owner,message):
    if 'launcher' in sys.argv[1:]:
        if 'debug' not in sys.argv[1:]:
            await Meowth.send_message(owner,message)
    print(message)
    logger.info(message)

async def maint_start():
    try:
        event_loop.create_task(server_cleanup())
        event_loop.create_task(channel_cleanup())
        logger.info("Maintenance Tasks Started")
    except KeyboardInterrupt as e:
        tasks.cancel()

event_loop = asyncio.get_event_loop()

"""

======================

End helper functions

======================

"""


"""
Meowth tracks raiding commands through the raidchannel_dict.
Each channel contains the following fields:
'trainer_dict' : a dictionary of all trainers interested in the raid.
'exp'          : an instance of time.struct_time tracking when the raid ends.
'active'       : a Boolean indicating whether the raid is still active.

The trainer_dict contains "trainer" elements, which have the following fields:
'status' : a string indicating either "omw" or "waiting"
'count'  : the number of trainers in the party
"""

team_msg = " or ".join(["**!team {0}**".format(team) for team in config['team_dict'].keys()])

@Meowth.event
async def on_ready():
    Meowth.owner = discord.utils.get(Meowth.get_all_members(),id=config["master"])
    await _print(Meowth.owner,_("Starting up...")) #prints to the terminal or cmd prompt window upon successful connection to Discord
    Meowth.uptime = datetime.datetime.now()
    owners = []
    msg_success = 0
    msg_fail = 0
    servers = len(Meowth.servers)
    users = 0
    for server in Meowth.servers:
        users += len(server.members)
        try:
            if server.id not in server_dict:
                server_dict[server.id] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'welcomechan': '', 'wantset': False, 'raidset': False, 'wildset': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}, 'autoraid': True, 'autoegg': True, 'autowild': True, 'raidlvls': [1,2,3,4,5], 'egglvls': [1,2,3,4,5]}
        except KeyError:
            server_dict[server.id] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'welcomechan': '', 'wantset': False, 'raidset': False, 'wildset': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}, 'autoraid': True, 'autoegg': True, 'autowild': True, 'raidlvls': [1,2,3,4,5], 'egglvls': [1,2,3,4,5]}

        owners.append(server.owner)

    await _print(Meowth.owner,_("Meowth! That's right!\n\n{server_count} servers connected.\n{member_count} members found.").format(server_count=servers,member_count=users))

    await maint_start()



@Meowth.event
async def on_server_join(server):
    owner = server.owner
    server_dict[server.id] = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'welcomechan': '', 'wantset': False, 'raidset': False, 'wildset': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}, 'autoraid': True, 'autoegg': True, 'autowild': True, 'raidlvls': [1,2,3,4,5], 'egglvls': [1,2,3,4,5]}
    await Meowth.send_message(owner, _("Meowth! I'm Meowth, a Discord helper bot for Pokemon Go communities, and someone has invited me to your server! Type **!help** to see a list of things I can do, and type **!configure** in any channel of your server to begin!"))

@Meowth.event
async def on_server_remove(server):
    try:
        if server.id in server_dict:
            try:
                del server_dict[server.id]
            except KeyError:
                pass
    except KeyError:
        pass

@Meowth.command(pass_context=True, hidden=True)
@commands.has_permissions(manage_server=True)
async def configure(ctx):
    server = ctx.message.server
    owner = ctx.message.author
    server_dict_check = {'want_channel_list': [], 'offset': 0, 'welcome': False, 'welcomechan': '', 'wantset': False, 'raidset': False, 'wildset': False, 'team': False, 'want': False, 'other': False, 'done': False, 'raidchannel_dict' : {}, 'autoraid': True, 'autoegg': True, 'autowild': True, 'raidlvls': [1,2,3,4,5], 'egglvls': [1,2,3,4,5]}
    server_dict_temp = copy.deepcopy(server_dict[server.id])
    firstconfig = False
    configcancel = False
    if server_dict_check == server_dict_temp:
        firstconfig = True
    try:
        if server_dict_temp['other']:
            pass
        else:
            pass
    except KeyError:
        server_dict_temp['other']=False
    try:
        if server_dict_temp['want_channel_list']:
            pass
        else:
            pass
    except KeyError:
        server_dict_temp['want_channel_list'] = []
    configmessage = "Meowth! That's Right! Welcome to the configuration for Meowth the Pokemon Go Helper Bot! I will be guiding you through some setup steps to get me setup on your server.\n\n**Role Setup**\nBefore you begin the configuration, please make sure my role is moved to the top end of the server role hierarchy. It can be under admins and mods, but must be above team ands general roles. [Here is an example](http://i.imgur.com/c5eaX1u.png)"
    if firstconfig == False:
        if server_dict_temp['other']:
            configreplylist = ['all','team','welcome','main','regions','raid','wild','want','timezone','allmain','huntr']
            configmessage += """\n\n**Welcome Back**\nThis isn't your first time configurating. You can either reconfigure everything by replying with **all** or reply with one of the following to configure that specific setting:\n\n**all** - To redo configuration\n**team** - For Team Assignment configuration\n**welcome** - For Welcome Message configuration\n**main** - For main command configuration\n**raid** - for raid command configuration\n**wild** - for wild command configuration\n**regions** - For configuration of reporting channels or map links\n**want** - for want/unwant command configuration and channel\n**timezone** - For timezone configuration\n**allmain** - For main, regions, raid, wild, want, timezone configuration\n**huntr** - For huntr integration configuration"""
            configmessage += "\n\nReply with **cancel** at any time throughout the questions to cancel the configure process."
            await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=configmessage).set_author(name=_("Meowth Configuration - {0}").format(server), icon_url=Meowth.user.avatar_url))
        else:
            configreplylist = ['all','team','welcome','main','allmain']
            configmessage += """\n\n**Welcome Back**\nThis isn't your first time configurating. You can either reconfigure everything by replying with **all** or reply with one of the following to configure that specific setting:\n\n**all** - To redo configuration\n**team** - For Team Assignment configuration\n**welcome** - For Welcome Message configuration\n**main** - For main command configuration\n**allmain** - For main, regions, raid, wild, want, timezone configuration"""
            configmessage += "\n\nReply with **cancel** at any time throughout the questions to cancel the configure process."
            await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=configmessage).set_author(name=_("Meowth Configuration - {0}").format(server), icon_url=Meowth.user.avatar_url))
        while True:
            configreply = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if configreply.content.lower() in configreplylist:
                configgoto = configreply.content.lower()
                break
            elif configreply.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            elif configreply.content.lower() not in configreplylist:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with one of the choices above."))
                continue
    elif firstconfig == True:
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=configmessage).set_author(name=_("Meowth Configuration - {0}").format(server), icon_url=Meowth.user.avatar_url))
    #configure team
    if configcancel == False and (firstconfig == True or configgoto == "all" or configgoto == "team"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="""Team assignment allows users to assign their Pokemon Go team role using the **!team** command. If you have a bot that handles this already, you may want to disable this feature.\n\nIf you are to use this feature, ensure existing team roles are as follows: mystic, valor, instinct. These must be all lowercase letters. If they don't exist yet, I'll make some for you instead.\n\nRespond with: **N** to disable, **Y** to enable:""").set_author(name="Team Assignments", icon_url=Meowth.user.avatar_url))
        while True:
            teamreply = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if teamreply.content.lower() == "y":
                server_dict_temp['team']=True
                for team in config['team_dict'].keys():
                    temp_role = discord.utils.get(server.roles, name=team)
                    if temp_role == None:
                        await Meowth.create_role(server = server, name = team, hoist = False, mentionable = True)
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Team Assignments enabled!"))
                break
            elif teamreply.content.lower() == "n":
                server_dict_temp['team']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Team Assignments disabled!"))
                break
            elif teamreply.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure welcome
    if configcancel == False and (firstconfig == True or configgoto == "all" or configgoto == "welcome"):
        welcomeconfig = "I can welcome new members to the server with a short message. Here is an example:\n\n"
        if server_dict_temp['team'] == True:
            welcomeconfig += _("Meowth! Welcome to {server_name}, {owner_name.mention}! Set your team by typing '**!team mystic**' or '**!team valor**' or '**!team instinct**' without quotations. If you have any questions just ask an admin.").format(server_name=server.name, owner_name=owner)
        else:
            welcomeconfig += _("Meowth! Welcome to {server_name}, {owner_name.mention}! If you have any questions just ask an admin.").format(server_name=server, owner_name=owner)
        welcomeconfig += "\n\nThis welcome message can be in a specific channel or a direct message. If you have a bot that handles this already, you may want to disable this feature.\n\nRespond with: **N** to disable, **Y** to enable:"
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=welcomeconfig).set_author(name="Welcome Message", icon_url=Meowth.user.avatar_url))
        while True:
            welcomereply = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if welcomereply.content.lower() == "y":
                server_dict_temp['welcome'] = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Welcome Message enabled!"))
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Which channel in your server would you like me to post the Welcome Messages? You can also choose to have them sent to the new member via Direct Message (DM) instead.\n\nRespond with: **channel-name** of a channel in your server or **DM** to Direct Message:").set_author(name="Welcome Message Channel", icon_url=Meowth.user.avatar_url))
                wchcheck = 0
                while True:
                    welcomechannelreply = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
                    if welcomechannelreply.content.lower() == "dm":
                        server_dict_temp['welcomechan'] = "dm"
                        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Welcome DM set"))
                        break
                    elif " " in welcomechannelreply.content.lower():
                        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Channel names can't contain spaces, sorry. Please double check the name and send your response again."))
                        continue
                    elif welcomechannelreply.content.lower() == "cancel":
                        configcancel = True
                        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                        return
                    else:
                        server_channel_list = []
                        for channel in server.channels:
                            server_channel_list.append(channel.name)
                        diff = set([welcomechannelreply.content.lower().strip()]) - set(server_channel_list)
                        if not diff:
                            server_dict_temp['welcomechan'] = welcomechannelreply.content.lower()
                            await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Welcome Channel set"))
                            break
                        else:
                            await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="The channel you provided isn't in your server. Please double check your channel name and resend your response."))
                            continue
                    break
                break
            elif welcomereply.content.lower() == "n":
                server_dict_temp['welcome'] = False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Welcome Message disabled!"))
                break
            elif welcomereply.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure main
    if configcancel == False and (firstconfig == True or configgoto == "all" or configgoto == "main" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Main Functions include:\n - **!want** and creating tracked Pokemon roles \n - **!wild** Pokemon reports\n - **!raid** reports and channel creation for raid management.\nIf you don't want __any__ of the Pokemon tracking or Raid management features, you may want to disable them.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Main Functions", icon_url=Meowth.user.avatar_url))
        while True:
            otherreply = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if otherreply.content.lower() == "y":
                server_dict_temp['other']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Main Functions enabled"))
                break
            elif otherreply.content.lower() == "n":
                server_dict_temp['other']=False
                server_dict_temp['raidset']=False
                server_dict_temp['wildset']=False
                server_dict_temp['wantset']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Main Functions disabled"))
                break
            elif otherreply.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure main-raid
    if configcancel == False and server_dict_temp['other'] is True and (firstconfig == True or configgoto == "all" or configgoto == "raid" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Do you want **!raid** reports enabled? If you want __only__ the **!wild** feature for reports, you may want to disable this.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Raid Reports", icon_url=Meowth.user.avatar_url))
        while True:
            raidconfigset = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if raidconfigset.content.lower() == "y":
                server_dict_temp['raidset']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Raid Reports enabled"))
                break
            elif raidconfigset.content.lower() == "n":
                server_dict_temp['raidset']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Raid Reports disabled"))
                break
            elif raidconfigset.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure main-wild
    if configcancel == False and server_dict_temp['other'] is True and (firstconfig == True or configgoto == "all" or configgoto == "wild" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Do you want **!wild** reports enabled? If you want __only__ the **!raid** feature for reports, you may want to disable this.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Wild Reports", icon_url=Meowth.user.avatar_url))
        while True:
            wildconfigset = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if wildconfigset.content.lower() == "y":
                server_dict_temp['wildset']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Wild Reports enabled"))
                break
            elif wildconfigset.content.lower() == "n":
                server_dict_temp['wildset']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Wild Reports disabled"))
                break
            elif wildconfigset.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure main-channels
    if configcancel == False and server_dict_temp['other'] is True and (server_dict_temp['wildset'] is True or server_dict_temp['raidset'] is True) and (firstconfig == True or configgoto == "all" or configgoto == "regions" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Pokemon raid or wild reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nIf you do not require raid and wild reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:").set_author(name="Reporting Channels", icon_url=Meowth.user.avatar_url))
        citychannel_dict = {}
        while True:
            citychannels = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if citychannels.content.lower() == "n":
                server_dict_temp['wildset']=False
                server_dict_temp['raidset']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Reporting Channels disabled"))
                break
            elif citychannels.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                citychannel_list = citychannels.content.lower().split(', ')
                server_channel_list = []
                for channel in server.channels:
                    server_channel_list.append(channel.name)
                diff = set(citychannel_list) - set(server_channel_list)
                if not diff:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Reporting Channels enabled"))
                    break
                else:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The channel list you provided doesn't match with your servers channels.\n\nThe following aren't in your server: {invalid_channels}\n\nPlease double check your channel list and resend your reponse.").format(invalid_channels=", ".join(diff))))
                    continue
    #configure main-locations
    if configcancel == False and server_dict_temp['other'] is True and (server_dict_temp['wildset'] is True or server_dict_temp['raidset'] is True) and (firstconfig == True or configgoto == "all" or configgoto == "regions" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="""For each report, I generate Google Maps links to give people directions to raids and spawns! To do this, I need to know which suburb/town/region each report channel represents, to ensure we get the right location in the map. For each report channel you provided, I will need it's corresponding general location using only letters and spaces, with each location seperated by a comma and space.\n\nExample: `kansas city mo, hull uk, sydney nsw australia`\n\nEach location will have to be in the same order as you provided the channels in the previous question.\n\nRespond with: **location info, location info, location info** each matching the order of the previous channel list:""").set_author(name="Report Locations", icon_url=Meowth.user.avatar_url))
        while True:
            cities = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if cities.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            city_list = cities.content.split(', ')
            if len(city_list) == len(citychannel_list):
                for i in range(len(citychannel_list)):
                    citychannel_dict[citychannel_list[i]]=city_list[i]
                break
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The number of cities don't match the number of channels you gave me earlier!\n\nI'll show you the two lists to compare:\n\n{channellist}\n{citylist}\n\nPlease double check that your locations match up with your provided channels and resend your response.").format(channellist=(", ".join(citychannel_list)), citylist=(", ".join(city_list)))))
                continue
        server_dict_temp['city_channels'] = citychannel_dict
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Report Locations are set"))
    #configure main-want
    if configcancel == False and server_dict_temp['other'] is True and (firstconfig == True or configgoto == "all" or configgoto == "want" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="""The **!want** and **!unwant** commands let you add or remove roles for Pokemon that will be mentioned in reports. This let you get notifications on the Pokemon you want to track. I just need to know what channels you want to allow people to manage their pokemon with the **!want** and **!unwant** command. If you pick a channel that doesn't exist, I'll make it for you.\n\nIf you don't ant to allow the management of tracked Pokemon roles, then you may want to disable this feature.\n\nRepond with: **N** to disable, or the **channel-name** list to enable, each seperated by a comma and space.""").set_author(name="Pokemon Notifications", icon_url=Meowth.user.avatar_url))
        while True:
            wantchs = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if wantchs.content.lower() == "n":
                server_dict_temp['wantset']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Pokemon Notifications disabled"))
                break
            elif wantchs.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                want_list = wantchs.content.lower().split(', ')
                server_channel_list = []
                for channel in server.channels:
                    server_channel_list.append(channel.name)
                diff = set(want_list) - set(server_channel_list)
                if not diff:
                    server_dict_temp['wantset']=True
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Pokemon Notifications enabled"))
                    while True:
                        try:
                            for want_channel_name in want_list:
                                want_channel = discord.utils.get(server.channels, name = want_channel_name)
                                if want_channel == None:
                                    want_channel = await Meowth.create_channel(server, want_channel_name)
                                if want_channel.id not in server_dict_temp['want_channel_list']:
                                    server_dict_temp['want_channel_list'].append(want_channel.id)
                            break
                        except:
                            await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! You didn't give me enough permissions to create channels! Please check my permissions and that my role is above general roles. Let me know if you'd like me to check again.\n\nRespond with: **Y** to try again, or **N** to skip and create the missing channels yourself.")))
                            while True:
                                wantpermswait = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
                                if wantpermswait.content.lower() == "n":
                                    break
                                elif wantpermswait.content.lower() == "y":
                                    break
                                elif wantpermswait.content.lower() == "cancel":
                                    configcancel = True
                                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                                    return
                                else:
                                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **Y** to try again, or **N** to skip and create the missing channels yourself."))
                                    continue
                            if wantpermswait.content.lower() == "y":
                                continue
                            break
                else:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The channel list you provided doesn't match with your servers channels.\n\nThe following aren't in your server:{invalid_channels}\n\nPlease double check your channel list and resend your reponse.").format(invalid_channels=", ".join(diff))))
                    continue
                break
    #configure main-timezone
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['raidset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "timezone" or configgoto == "allmain"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("To help coordinate raids reports for you, I need to know what timezone you're in! The current 24-hr time UTC is {utctime}. How many hours off from that are you?\n\nRespond with: A number from **-12** to **12**:").format(utctime=strftime("%H:%M",time.gmtime()))).set_author(name="Timezone Configuration", icon_url=Meowth.user.avatar_url))
        while True:
            offsetmsg = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if offsetmsg.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                try:
                    offset = float(offsetmsg.content)
                except ValueError:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I couldn't convert your answer to an appropriate timezone!.\n\nPlease double check what you sent me and resend a number strarting from **-12** to **12**."))
                    continue
                if not -12 <= offset <= 14:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I couldn't convert your answer to an appropriate timezone!.\n\nPlease double check what you sent me and resend a number strarting from **-12** to **12**."))
                    continue
                else:
                    break
        server_dict_temp['offset'] = offset
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Timezone set"))
    #configure huntr-raid
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['raidset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "huntr"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Do you want automatic **!raid** reports using @GymHuntrBot enabled?\n\nAny raid that @GymHuntrBot posts in a channel that Meowth also has access to will be converted to a **!raid** report. If enabled, there are more options available for configuring this setting.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Automatic Raid Reports", icon_url=Meowth.user.avatar_url))
        while True:
            wildconfigset = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if wildconfigset.content.lower() == "y":
                server_dict_temp['autoraid']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Automatic Raid Reports enabled"))
                break
            elif wildconfigset.content.lower() == "n":
                server_dict_temp['autoraid']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Automatic Raid Reports disabled"))
                break
            elif wildconfigset.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure huntr-raid-levels
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['raidset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "huntr"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter the levels that you would like Meowth to create automatic raid channels for, separated by a comma. For example: `3,4,5`\n\nIn this example, if **!level 1** for @GymHuntrBot is used, level 1 and 2 raids will have a re-stylized raid report with a @mention, but no channel will be created. However, all level 3+ raids will have a channel created.\n\nUse both this configuration and @GymHuntrBot's commands to customize to your needs.").set_author(name="Automatic Raid Report Levels", icon_url=Meowth.user.avatar_url))
        raidlevel_list = []
        server_dict_temp['raidlvls'] = []
        while True:
            raidlevels = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if raidlevels.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            elif raidlevels.content.lower() == "n":
                server_dict_temp['autoraid']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Automatic Raid Reports disabled"))
                break
            else:
                raidlevel_list = raidlevels.content.lower().split(',')
                for level in raidlevel_list:
                    if level.isdigit() and int(level) <=5 and int(level) >0:
                        server_dict_temp['raidlvls'].append(int(level))
                if len(server_dict_temp['raidlvls']) > 0:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description=_("Automatic Raid Channel Levels set to: {levels}").format(levels=",".join(str(x) for x in server_dict_temp['raidlvls']))))
                    break
                else:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter at least one number from 1 to 5 separated by comma. Ex: `1,2,3`. Or **N** to turn off automatic raids."))
                    continue
    #configure huntr-raidegg
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['raidset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "huntr"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Do you want automatic **!raidegg** reports using @GymHuntrBot enabled?\n\nAny egg that @GymHuntrBot posts in a channel that Meowth also has access to will be converted to a **!raidegg** report.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Automatic Egg Reports", icon_url=Meowth.user.avatar_url))
        while True:
            wildconfigset = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if wildconfigset.content.lower() == "y":
                server_dict_temp['autoegg']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Automatic Egg Reports enabled"))
                break
            elif wildconfigset.content.lower() == "n":
                server_dict_temp['autoegg']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Automatic Egg Reports disabled"))
                break
            elif wildconfigset.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    #configure huntr-egg-levels
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['raidset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "huntr"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter the levels that you would like Meowth to create automatic egg channels for, separated by a comma. For example: `3,4,5`\n\nIn this example, if **!level 1** for @GymHuntrBot is used, level 1 and 2 eggs will have a re-stylized egg report with a @mention, but no channel will be created. However, all level 3+ eggs will have a channel created.\n\nUse both this configuration and @GymHuntrBot's commands to customize to your needs.").set_author(name="Automatic Egg Report Levels", icon_url=Meowth.user.avatar_url))
        egglevel_list = []
        server_dict_temp['egglvls'] = []
        while True:
            egglevels = await Meowth.wait_for_message(author = owner, check=lambda message: message.server is None)
            if egglevels.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            elif egglevels.content.lower() == "n":
                server_dict_temp['autoegg']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Automatic Egg Reports disabled"))
                break
            else:
                egglevel_list = egglevels.content.lower().split(',')
                for level in egglevel_list:
                    if level.isdigit() and int(level) <=5 and int(level) >0:
                        server_dict_temp['egglvls'].append(int(level))
                if len(server_dict_temp['egglvls']) > 0:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description=_("Automatic Egg Channel Levels set to: {levels}").format(levels=",".join(str(x) for x in server_dict_temp['egglvls']))))
                    break
                else:
                    await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter at least one number from 1 to 5 separated by comma. Ex: `1,2,3`. Or **N** to turn off automatic eggs."))
                    continue
    #configure huntr-wild
    if configcancel == False and server_dict_temp['other'] is True and server_dict_temp['wildset'] is True and (firstconfig == True or configgoto == "all" or configgoto == "huntr"):
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Do you want automatic **!wild** reports using @HuntrBot enabled?\n\nAnything that @HuntrBot posts in a channel that Meowth also has access to will be converted to a **!wild** report.\n\nRespond with: **N** to disable, or **Y** to enable:").set_author(name="Automatic Wild Reports", icon_url=Meowth.user.avatar_url))
        while True:
            wildconfigset = await Meowth.wait_for_message(author=owner, check=lambda message: message.server is None)
            if wildconfigset.content.lower() == "y":
                server_dict_temp['autowild']=True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.green(), description="Automatic Wild Reports enabled"))
                break
            elif wildconfigset.content.lower() == "n":
                server_dict_temp['autowild']=False
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="Automatic Wild Reports disabled"))
                break
            elif wildconfigset.content.lower() == "cancel":
                configcancel = True
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.red(), description="**CONFIG CANCELLED!**\n\nNo changes have been made."))
                return
            else:
                await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
    server_dict_temp['done']=True
    if configcancel == False:
        server_dict[server.id] = server_dict_temp
        await Meowth.send_message(owner, embed=discord.Embed(colour=discord.Colour.lighter_grey(), description="Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again."))

@Meowth.event
async def on_member_join(member):
    """Welcome message to the server and some basic instructions."""
    server = member.server
    if server_dict[server.id]['done'] == False or server_dict[server.id]['welcome'] == False:
        return

    # Build welcome message

    admin_message = _(" If you have any questions just ask an admin.")

    welcomemessage = _("Meowth! Welcome to {server_name}, {new_member_name}! ")
    if server_dict[server.id]['team'] == True:
        welcomemessage += _("Set your team by typing {team_command}.").format(team_command=team_msg)
    welcomemessage += admin_message

    if server_dict[server.id]['welcomechan'] == "dm":
        await Meowth.send_message(member, welcomemessage.format(server_name=server.name, new_member_name=member.mention))

    else:
        default = discord.utils.get(server.channels, name = server_dict[server.id]['welcomechan'])
        if not default:
            pass
        else:
            await Meowth.send_message(default, welcomemessage.format(server_name=server.name, new_member_name=member.mention))


"""

Admin commands

"""

async def _save():
    with tempfile.NamedTemporaryFile('wb', dir=os.path.dirname(os.path.join('data', 'serverdict')), delete=False) as tf:
        pickle.dump(server_dict, tf, -1)
        tempname = tf.name
    try:
        os.remove(os.path.join('data', 'serverdict_backup'))
    except OSError as e:
        pass
    try:
        os.rename(os.path.join('data', 'serverdict'), os.path.join('data', 'serverdict_backup'))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    os.rename(tempname, os.path.join('data', 'serverdict'))

@Meowth.command(pass_context=True)
@checks.is_owner()
async def reload_json(ctx):
    load_config()
    await Meowth.add_reaction(ctx.message, '✅')


@Meowth.command(pass_context=True)
@checks.is_owner()
async def exit(ctx):
    """Exit after saving.

    Usage: !exit.
    Calls the save function and quits the script."""
    try:
        await _save()
    except Exception as err:
        await _print(Meowth.owner,_("Error occured while trying to save!"))
        await _print(Meowth.owner,err)

    await Meowth.send_message(ctx.message.channel,"Shutting down...")
    Meowth._shutdown_mode = 0
    await Meowth.logout()

@Meowth.command(pass_context=True)
@checks.is_owner()
async def restart(ctx):
    """Restart after saving.

    Usage: !restart.
    Calls the save function and restarts Meowth."""
    try:
        await _save()
    except Exception as err:
        await _print(Meowth.owner,_("Error occured while trying to save!"))
        await _print(Meowth.owner,err)

    await Meowth.send_message(ctx.message.channel,"Restarting...")

    Meowth._shutdown_mode = 26
    await Meowth.logout()

@Meowth.command(pass_context=True)
@checks.is_owner()
async def save(ctx):
    """Save persistent state to file.

    Usage: !save
    File path is relative to current directory."""
    try:
        await _save()
        logger.info("CONFIG SAVED")
    except Exception as err:
        await _print(Meowth.owner,_("Error occured while trying to save!"))
        await _print(Meowth.owner,err)

@Meowth.command(pass_context=True, hidden=True)
@commands.has_permissions(manage_server=True)
async def outputlog(ctx):
    """Get current Meowth log.

    Usage: !outputlog
    Output is a link to hastebin."""
    with open(os.path.join('logs', 'meowth.log'), 'r', encoding='latin-1', errors='replace') as logfile:
        logdata=logfile.read()
    await Meowth.send_message(ctx.message.channel, hastebin.post(logdata))

@Meowth.command(pass_context=True)
@checks.is_owner()
async def welcome(ctx, user: discord.Member = None):
    """Test welcome on yourself or mentioned member.

    Usage: !welcome [@member]"""
    if not user:
        user = ctx.message.author
    await on_member_join(user)

@Meowth.group(pass_context=True, name="set")
@commands.has_permissions(manage_server=True)
async def _set(ctx):
    """Changes a setting."""
    if ctx.invoked_subcommand is None:
        pages = bot.formatter.format_help_for(ctx,ctx.command)
        for page in pages:
            await bot.send_message(ctx.message.channel, page)

@_set.command(pass_context=True)
@commands.has_permissions(manage_server=True)
async def prefix(ctx,prefix=None):
    """Changes server prefix."""
    if prefix == "clear":
        prefix=None

    _set_prefix(Meowth,ctx.message.server,prefix)

    if prefix is not None:
        await Meowth.send_message(ctx.message.channel,"Prefix has been set to: `{}`".format(prefix))
    else:
        default_prefix = Meowth.config["default_prefix"]
        await Meowth.send_message(ctx.message.channel,"Prefix has been reset to default: `{}`".format(default_prefix))

@Meowth.group(pass_context=True, name="get")
async def _get(ctx):
    """Get a setting value"""
    if ctx.invoked_subcommand is None:
        pages = bot.formatter.format_help_for(ctx,ctx.command)
        for page in pages:
            await bot.send_message(ctx.message.channel, page)

@_get.command(pass_context=True)
@commands.has_permissions(manage_server=True)
async def prefix(ctx):
    """Get server prefix."""
    prefix = _get_prefix(Meowth,ctx.message)
    await Meowth.send_message(ctx.message.channel,"Prefix for this server is: `{}`".format(prefix))

@Meowth.command(pass_context=True)
@commands.has_permissions(manage_server=True)
async def announce(ctx,*,announce=None):
    """Repeats your message in an embed from Meowth.

    Usage: !announce [announcement]
    If the announcement isn't added at the same time as the command, Meowth will wait 3 minutes for a followup message containing the announcement."""
    message = ctx.message
    channel = message.channel
    server = message.server
    author = message.author
    if announce is None:
        announcewait = await Meowth.send_message(channel, "I'll wait for your announcement!")
        announcemsg = await Meowth.wait_for_message(author=ctx.message.author, timeout=180)
        await Meowth.delete_message(announcewait)
        if announcemsg is not None:
            announce = announcemsg.content
            await Meowth.delete_message(announcemsg)
        else:
            confirmation = await Meowth.send_message(channel, "Meowth! You took too long to send me your announcement! Retry when you're ready.")
    embeddraft = discord.Embed(colour=server.me.colour, description=announce)
    title = "Announcement"
    if Meowth.user.avatar_url:
        embeddraft.set_author(name=title, icon_url=Meowth.user.avatar_url)
    else:
        embeddraft.set_author(name=title)
    draft = await Meowth.send_message(channel,embed=embeddraft)
    def check(react,user):
        if user.id is not author.id:
            return False
        return True
    reaction_list = ['❔','✅','❎']
    owner_msg_add = ""
    if checks.is_owner_check(ctx):
        owner_msg_add = "🌎 to send it to all servers, "
        reaction_list.insert(0,'🌎')
    rusure = await Meowth.send_message(channel,_("That's what you sent, does it look good? React with {}❔ to send to another channel, ✅ to send it to this channel, or ❎ to cancel").format(owner_msg_add))
    for r in reaction_list:
        await asyncio.sleep(0.25)
        await Meowth.add_reaction(rusure,r)
    res = await Meowth.wait_for_reaction(reaction_list, message=rusure, check=check, timeout=60)
    if res is not None:
        await Meowth.delete_message(rusure)
        if res.reaction.emoji == "❎":
            confirmation = await Meowth.send_message(channel,_("Announcement Cancelled."))
            await Meowth.delete_message(draft)
        elif res.reaction.emoji == "✅":
            confirmation = await Meowth.send_message(channel,_("Announcement Sent."))
        elif res.reaction.emoji == "❔":
            channelwait = await Meowth.send_message(channel, "What channel would you like me to send it to?")
            channelmsg = await Meowth.wait_for_message(author=ctx.message.author, timeout=60)
            try:
                sendchannel = commands.ChannelConverter(ctx, str(channelmsg.content).strip()).convert()
            except commands.BadArgument:
                sendchannel = None
            if channelmsg is not None and sendchannel is not None:
                announcement = await Meowth.send_message(sendchannel, embed=embeddraft)
                confirmation = await Meowth.send_message(channel,_("Announcement Sent."))
            elif sendchannel is None:
                confirmation = await Meowth.send_message(channel, "Meowth! That channel doesn't exist! Retry when you're ready.")
            else:
                confirmation = await Meowth.send_message(channel, "Meowth! You took too long to send me your announcement! Retry when you're ready.")
            await Meowth.delete_message(channelwait)
            await Meowth.delete_message(channelmsg)
            await Meowth.delete_message(draft)
        elif res.reaction.emoji == "🌎" and checks.is_owner_check(ctx):
            failed = 0
            sent = 0
            count = 0
            recipients = {}
            embeddraft.set_footer(text="For support, contact us on our Discord server. Invite Code: hhVjAN8")
            embeddraft.colour = discord.Colour.lighter_grey()
            for server in Meowth.servers:
                recipients[server.name] = server.owner
            for server, destination in recipients.items():
                try:
                    await Meowth.send_message(destination,embed=embeddraft)
                except discord.HTTPException:
                    failed += 1
                    logger.info("Announcement Delivery Failure: {} - {}".format(destination.name,server))
                else:
                    sent += 1
                count += 1
            logger.info("Announcement sent to {} server owners: {} successful, {} failed.".format(count,sent,failed))
            confirmation = await Meowth.send_message(channel,"Announcement sent to {} server owners: {} successful, {} failed.".format(count, sent, failed))
        await asyncio.sleep(10)
        await Meowth.delete_message(confirmation)
    else:
        await Meowth.delete_message(rusure)
        confirmation = await Meowth.send_message(channel,_("Announcement Timed Out."))
        await asyncio.sleep(10)
        await Meowth.delete_message(confirmation)
    await asyncio.sleep(30)
    await Meowth.delete_message(message)

"""

End admin commands

"""
async def _uptime(bot):
    """Shows info about Meowth"""
    time_start = bot.uptime
    time_now = datetime.datetime.now()
    ut = (relativedelta(time_now,time_start))
    ut.years, ut.months, ut.days, ut.hours, ut.minutes
    if ut.years >= 1:
        uptime = "{yr}y {mth}m {day}d {hr}:{min}".format(yr=ut.years,mth=ut.months,day=ut.days,hr=ut.hours,min=ut.minutes)
    elif ut.months >= 1:
        uptime = "{mth}m {day}d {hr}:{min}".format(mth=ut.months,day=ut.days,hr=ut.hours,min=ut.minutes)
    elif ut.days >= 1:
        uptime = "{day} days {hr} hrs {min} mins".format(day=ut.days,hr=ut.hours,min=ut.minutes)
    elif ut.hours >= 1:
        uptime = "{hr} hrs {min} mins {sec} secs".format(hr=ut.hours,min=ut.minutes,sec=ut.seconds)
    else:
        uptime = "{min} mins {sec} secs".format(min=ut.minutes,sec=ut.seconds)

    return uptime

@Meowth.command(pass_context=True, name="uptime")
async def cmd_uptime(ctx):
    """Shows Meowth's uptime"""
    server = ctx.message.server
    channel = ctx.message.channel
    embed_colour = server.me.colour or discord.Colour.lighter_grey()
    uptime_str = await _uptime(Meowth)
    embed = discord.Embed(colour=embed_colour,icon_url=Meowth.user.avatar_url)
    embed.add_field(name="Uptime", value=uptime_str)
    try:
        await Meowth.send_message(channel,embed=embed)
    except discord.HTTPException:
        await Meowth.send_message(channel,"I need the `Embed links` permission to send this")

@Meowth.command(pass_context=True)
async def about(ctx):
    """Shows info about Meowth"""
    author_repo = "https://github.com/FoglyOgly"
    author_name = "FoglyOgly"
    huntr_repo = "https://github.com/doonce/Meowth"
    huntr_name = "BrenenP"
    bot_repo = author_repo + "/Meowth"
    server_url = "https://discord.gg/hhVjAN8"
    owner = Meowth.owner
    channel = ctx.message.channel
    uptime_str = await _uptime(Meowth)
    embed_colour = ctx.message.server.me.colour or discord.Colour.lighter_grey()

    about = (
        "I'm Meowth! A Pokemon Go helper bot for Discord!\n\n"
        "I'm made by [{author_name}]({author_repo}) and improvements have been contributed by many other people also.\n\n"
        "Huntr integration was implemented by [{huntr_name}]({huntr_repo}).\n\n"
        "[Join our server]({server_invite}) if you have any questions or feedback.\n\n"
        "".format(author_name=author_name,author_repo=author_repo,huntr_name=huntr_name,huntr_repo=huntr_repo,server_invite=server_url))

    member_count = 0
    server_count = 0
    for server in Meowth.servers:
        server_count += 1
        member_count += len(server.members)

    embed = discord.Embed(colour=embed_colour,icon_url=Meowth.user.avatar_url)
    embed.add_field(name="About Meowth", value=about, inline=False)
    embed.add_field(name="Owner", value=owner)
    embed.add_field(name="Servers", value=server_count)
    embed.add_field(name="Members", value=member_count)
    embed.add_field(name="Uptime", value=uptime_str)
    embed.set_footer(text="For support, contact us on our Discord server. Invite Code: hhVjAN8")

    try:
        await Meowth.send_message(channel,embed=embed)
    except discord.HTTPException:
        await Meowth.send_message(channel,"I need the `Embed links` permission to send this")

@Meowth.command(pass_context = True)
@checks.teamset()
@checks.nonraidchannel()
async def team(ctx):
    """Set your team role.

    Usage: !team <team name>
    The team roles have to be created manually beforehand by the server administrator."""

    server = ctx.message.server
    toprole = server.me.top_role.name
    position = server.me.top_role.position
    high_roles = []

    for team in config['team_dict'].keys():
        temp_role = discord.utils.get(server.roles, name=team)
        if not temp_role:
            temp_role = await Meowth.create_role(server, name=team)
        if temp_role.position > position:
            high_roles.append(temp_role.name)

    if high_roles:
        await Meowth.send_message(ctx.message.channel, _("Meowth! My roles are ranked lower than the following team roles: **{higher_roles_list}**\nPlease get an admin to move my roles above them!").format(higher_roles_list=', '.join(high_roles)))
        return

    role = None
    team_split = ctx.message.clean_content.lower().split()
    del team_split[0]
    entered_team = team_split[0]
    role = discord.utils.get(ctx.message.server.roles, name=entered_team)

    # Check if user already belongs to a team role by
    # getting the role objects of all teams in team_dict and
    # checking if the message author has any of them.
    for team in config['team_dict'].keys():
        temp_role = discord.utils.get(ctx.message.server.roles, name=team)
        # If the role is valid,
        if temp_role:
            # and the user has this role,
            if temp_role in ctx.message.author.roles:
                # then report that a role is already assigned
                await Meowth.send_message(ctx.message.channel, _("Meowth! You already have a team role!"))
                return
        # If the role isn't valid, something is misconfigured, so fire a warning.
        else:
            await Meowth.send_message(ctx.message.channel,_("Meowth! {team_role} is not configured as a role on this server. Please contact an admin for assistance.").format(team_role=team))
    # Check if team is one of the three defined in the team_dict

    if entered_team not in config['team_dict'].keys():
        await Meowth.send_message(ctx.message.channel, _("Meowth! \"{entered_team}\" isn't a valid team! Try {available_teams}").format(entered_team=entered_team, available_teams=team_msg))
        return
    # Check if the role is configured on the server
    elif role is None:
        await Meowth.send_message(ctx.message.channel, _("Meowth! The \"{entered_team}\" role isn't configured on this server! Contact an admin!").format(entered_team=entered_team))
    else:
        try:
            await Meowth.add_roles(ctx.message.author, role)
            await Meowth.send_message(ctx.message.channel, _("Meowth! Added {member} to Team {team_name}! {team_emoji}").format(member=ctx.message.author.mention, team_name=role.name.capitalize(), team_emoji=parse_emoji(ctx.message.server, config['team_dict'][entered_team])))
        except discord.Forbidden:
            await Meowth.send_message(ctx.message.channel, _("Meowth! I can't add roles!"))

@Meowth.command(pass_context = True)
@checks.wantset()
@checks.nonraidchannel()
@checks.wantchannel()
async def want(ctx):
    """Add a Pokemon to your wanted list.

    Usage: !want <species>
    Meowth will mention you if anyone reports seeing
    this species in their !wild or !raid command."""

    """Behind the scenes, Meowth tracks user !wants by
    creating a server role for the Pokemon species, and
    assigning it to the user."""
    message = ctx.message
    server = message.server
    channel = message.channel
    want_split = message.clean_content.lower().split()
    del want_split[0]
    entered_want = " ".join(want_split)
    entered_want = get_name(entered_want).lower() if entered_want.isdigit() else entered_want
    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_want)), None)
    if pkmn_match:
        entered_want = pkmn_match
    else:
        await Meowth.send_message(message.channel, spellcheck(entered_want))
        return
    role = discord.utils.get(server.roles, name=entered_want)
    # Create role if it doesn't exist yet
    if role is None:
        role = await Meowth.create_role(server = server, name = entered_want, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)

    # If user is already wanting the Pokemon,
    # print a less noisy message
    if role in ctx.message.author.roles:
        await Meowth.add_reaction(message, '✅')
    else:
        await Meowth.add_roles(message.author, role)
        want_number = pkmn_info['pokemon_list'].index(entered_want) + 1
        await Meowth.add_reaction(message, '✅')

@Meowth.group(pass_context=True)
@checks.wantset()
@checks.nonraidchannel()
@checks.wantchannel()
async def unwant(ctx):
    """Remove a Pokemon from your wanted list.

    Usage: !unwant <species>
    You will no longer be notified of reports about this Pokemon."""

    """Behind the scenes, Meowth removes the user from
    the server role for the Pokemon species."""
    message = ctx.message
    server = message.server
    channel = message.channel
    if ctx.invoked_subcommand is None:
        unwant_split = message.clean_content.lower().split()
        del unwant_split[0]
        entered_unwant = " ".join(unwant_split)
        entered_unwant = get_name(entered_unwant).lower() if entered_unwant.isdigit() else entered_unwant
        rgx = r"[^a-zA-Z0-9]"
        pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_unwant)), None)
        if pkmn_match:
            entered_unwant = pkmn_match
        else:
            await Meowth.send_message(message.channel, spellcheck(entered_unwant))
            return
        # If user is not already wanting the Pokemon,
        # print a less noisy message
        role = discord.utils.get(server.roles, name=entered_unwant)
        if role not in message.author.roles:
            await Meowth.add_reaction(message, '✅')
        else:
            await Meowth.remove_roles(message.author, role)
            unwant_number = pkmn_info['pokemon_list'].index(entered_unwant) + 1
            await Meowth.add_reaction(message, '✅')

@unwant.command(pass_context=True)
@checks.wantset()
@checks.nonraidchannel()
@checks.wantchannel()
async def all(ctx):
    """Remove all Pokemon from your wanted list.

    Usage: !unwant all
    All Pokemon roles are removed."""

    """Behind the scenes, Meowth removes the user from
    the server role for the Pokemon species."""
    message = ctx.message
    server = message.server
    channel = message.channel
    author = message.author
    await Meowth.send_typing(channel)
    count = 0
    roles = author.roles
    remove_roles = []
    for role in roles:
        if role.name in pkmn_info['pokemon_list']:
            remove_roles.append(role)
            count += 1
        continue
    await Meowth.remove_roles(author, *remove_roles)
    if count == 0:
        await Meowth.send_message(channel, content=_("{0}, you have no pokemon in your want list.").format(author.mention, count))
        return
    await Meowth.send_message(channel, content=_("{0}, I've removed {1} pokemon from your want list.").format(author.mention, count))
    return

@Meowth.command(pass_context = True)
@checks.wildset()
@checks.citychannel()
async def wild(ctx):
    """Report a wild Pokemon spawn location.

    Usage: !wild <species> <location>
    Meowth will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in."""
    huntr = False
    await _wild(ctx.message, huntr)

async def _wild(message, huntr):
    if not huntr:
        wild_split = message.clean_content.lower().split()
        huntrexp = ""
        huntrweather = "\u200b"
    else:
        wild_split = huntr.split("|")[0].lower().split()
        huntrexp = huntr.split("|")[1]
        huntrweather = "Weather: "+huntr.split("|")[2]
    del wild_split[0]
    if len(wild_split) <= 1:
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**"))
        return
    content = " ".join(wild_split)
    entered_wild = content.split(' ',1)[0]
    entered_wild = get_name(entered_wild).lower() if entered_wild.isdigit() else entered_wild
    spellone = spellcheck(entered_wild).split('"')[3]
    wild_details = content.split(' ',1)[1]
    if entered_wild not in pkmn_info['pokemon_list']:
        entered_wild2 = ' '.join([content.split(' ',2)[0],content.split(' ',2)[1]])
        if entered_wild2 in pkmn_info['pokemon_list']:
            entered_wild = entered_wild2
            try:
                wild_details = content.split(' ',2)[2]
            except IndexError:
                await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**"))
                return
        else:
            spelltwo = spellcheck(entered_wild2).split('"')[3]

    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_wild)), None)
    if pkmn_match:
        entered_wild = pkmn_match
    else:
        await Meowth.send_message(message.channel, spellcheck(entered_wild))
        return

    wild = discord.utils.get(message.server.roles, name = entered_wild)
    if wild is None:
        wild = await Meowth.create_role(server = message.server, name = entered_wild, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    wild_number = pkmn_info['pokemon_list'].index(entered_wild) + 1
    wild_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/pkmn/{0}_.png?cache=0".format(str(wild_number).zfill(3))
    if not huntr:
        wild_gmaps_link = create_gmaps_query(wild_details, message.channel)
        wild_embed = discord.Embed(title=_("Meowth! Click here for my directions to the wild {pokemon}!").format(pokemon=entered_wild.capitalize()),description=_("Ask {author} if my directions aren't perfect!").format(author=message.author.name),url=wild_gmaps_link,colour=message.server.me.colour)
        wild_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}").format(pokemon=entered_wild.capitalize(),pokemonnumber=str(wild_number),type="".join(get_type(message.server, wild_number)),inline=True))
    else:
        wild_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(wild_details)
        wild_embed = discord.Embed(title=_("Meowth! Click here for exact directions to the wild {pokemon}!").format(pokemon=entered_wild.capitalize()),url=wild_gmaps_link,colour=message.server.me.colour)
        wild_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}").format(pokemon=entered_wild.capitalize(),pokemonnumber=str(wild_number),type="".join(get_type(message.server, wild_number)),inline=True))
        wild_embed.add_field(name="**Despawns in:**", value=_("{huntrexp}").format(huntrexp=huntrexp),inline=True)
        wild_embed.add_field(name=huntrweather, value=_("Perform a scan to help find more by clicking [here](https://pokehuntr.com/#{huntrurl}).").format(huntrurl=wild_details), inline=False)
    wild_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
    wild_embed.set_thumbnail(url=wild_img_url)
    wildreportmsg = await Meowth.send_message(message.channel, content=_("Meowth! Wild {pokemon} reported by {member}! Details: {location_details}").format(pokemon=wild.mention, member=message.author.mention, location_details=wild_details),embed=wild_embed)
    if huntr:
        despawn = (int(huntrexp.split(" ")[0])*60) + int(huntrexp.split(" ")[2])
    else:
        despawn = 3600
    expiremsg = _("**This {pokemon} has despawned!**").format(pokemon=entered_wild.capitalize())
    await asyncio.sleep(despawn)
    try:
        await Meowth.edit_message(wildreportmsg, embed=discord.Embed(description=expiremsg,colour=message.server.me.colour))
    except discord.errors.NotFound:
        pass

@Meowth.command(pass_context=True)
@checks.cityeggchannel()
@checks.raidset()
async def raid(ctx):
    """Report an ongoing raid.

    Usage: !raid <species> <location> [minutes]
    Meowth will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in.
    Meowth's message will also include the type weaknesses of the boss.

    Finally, Meowth will create a separate channel for the raid report, for the purposes of organizing the raid."""
    huntr = False
    await _raid(ctx.message, huntr)

async def _raid(message, huntr):
    fromegg = False
    if message.channel.name not in server_dict[message.server.id]['city_channels'].keys():
        if message.channel.id in server_dict[message.channel.server.id]['raidchannel_dict'] and server_dict[message.channel.server.id]['raidchannel_dict'][message.channel.id]['type'] == 'egg':
            fromegg = True
        else:
            await Meowth.send_message(message.channel, _("Meowth! Please restrict raid reports to a city channel!"))
            return
    if not huntr:
        raid_split = message.clean_content.lower().split()
        gymhuntrgps = False
        gymhuntrmoves = False
    else:
        raid_split = huntr.split("|")[0].lower().split()
        gymhuntrgps = huntr.split("|")[1]
        gymhuntrmoves = huntr.split("|")[2]
    del raid_split[0]
    if len(raid_split) == 0:
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**"))
        return
    if raid_split[0] == "egg":
        await _raidegg(message, huntr=False)
        return
    if fromegg is True:
        eggdetails = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]
        egglevel = eggdetails['egglevel']
        if raid_split[0] == 'assume':
            if config['allow_assume'][egglevel] == "False":
                await Meowth.send_message(message.channel, _("Meowth! **!raid assume** is not allowed in this level egg."))
                return
            if server_dict[message.channel.server.id]['raidchannel_dict'][message.channel.id]['active'] == False:
                await _eggtoraid(raid_split[1].lower(), message.channel, huntr=False)
                return
            else:
                await _eggassume(" ".join(raid_split), message.channel)
                return
        else:
            if server_dict[message.channel.server.id]['raidchannel_dict'][message.channel.id]['active'] == False:
                await _eggtoraid(" ".join(raid_split).lower(), message.channel, huntr=False)
                return
            else:
                await Meowth.send_message(message.channel, _("Meowth! Please wait until the egg has hatched before changing it to an open raid!"))
                return
    entered_raid = re.sub("[\@]", "", raid_split[0].lower())
    entered_raid = get_name(entered_raid).lower() if entered_raid.isdigit() else entered_raid
    del raid_split[0]

    if raid_split[-1].isdigit():
        raidexp = int(raid_split[-1])
        del raid_split[-1]
    elif ":" in raid_split[-1]:
        raid_split[-1] = re.sub(r"[a-zA-Z]", "", raid_split[-1])
        if raid_split[-1].split(":")[0] == "":
            endhours = 0
        else:
            endhours = int(raid_split[-1].split(":")[0])
        if raid_split[-1].split(":")[1] == "":
            endmins = 0
        else:
            endmins = int(raid_split[-1].split(":")[1])
        raidexp = 60 * endhours + endmins
        del raid_split[-1]
    else:
        raidexp = False

    if raidexp and not huntr:
        if _timercheck(raidexp, raid_info["raid_eggs"][get_level(entered_raid)]['raidtime']):
            await Meowth.send_message(message.channel, _("Meowth...that's too long. Level {raidlevel} raids currently last no more than {raidtime} minutes...").format(raidlevel=get_level(entered_raid), raidtime=raid_info["raid_eggs"][get_level(entered_raid)]['raidtime']))
            return

    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_raid)), None)
    if pkmn_match:
        entered_raid = pkmn_match
    else:
        await Meowth.send_message(message.channel, spellcheck(entered_raid))
        return

    raid_match = True if entered_raid in get_raidlist() else False
    if not raid_match:
        await Meowth.send_message(message.channel, _("Meowth! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
        return
    raid_details = " ".join(raid_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**"))
        return
    if not huntr:
        raid_gmaps_link = create_gmaps_query(raid_details, message.channel)
    else:
        raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(huntr.split("|")[1])
    raid_channel_name = entered_raid + "-" + sanitize_channel_name(raid_details)
    raid_channel = await Meowth.create_channel(message.server, raid_channel_name, *message.channel.overwrites)
    raid = discord.utils.get(message.server.roles, name = entered_raid)
    if raid is None:
        raid = await Meowth.create_role(server = message.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/pkmn/{0}_.png?cache=0".format(str(raid_number).zfill(3))
    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the raid!"),url=raid_gmaps_link,colour=message.server.me.colour)
    raid_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}").format(pokemon=entered_raid.capitalize(),pokemonnumber=str(raid_number),type="".join(get_type(message.server, raid_number)),inline=True))
    raid_embed.add_field(name="**Weaknesses:**", value=_("{weakness_list}").format(weakness_list=weakness_to_str(message.server, get_weaknesses(entered_raid))),inline=True)
    if huntr:
        raid_embed.add_field(name=gymhuntrmoves, value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
    raid_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
    raid_embed.set_thumbnail(url=raid_img_url)
    raidreport = await Meowth.send_message(message.channel, content = _("Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention),embed=raid_embed)
    await asyncio.sleep(1) #Wait for the channel to be created.

    raidmsg = _("""Meowth! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!

To update your status, choose from the following commands: **!maybe**, **!coming**, **!here**, **!cancel**. If you are bringing more than one trainer/account, add in the number of accounts total on your first status update.
Example: `!coming 5`

To see the list of trainers who have given their status:
**!list interested**, **!list coming**, **!list here** or use just **!list** to see all lists. Use **!list teams** to see team distribution.

Sometimes I'm not great at directions, but I'll correct my directions if anybody sends me a maps link or uses **!location new <address>**. You can see the location of a raid by using **!location**

You can set the time remaining with **!timerset <minutes>** and access this with **!timer**.
You can set the start time with **!starttime [HH:MM AM/PM]** and access this with **!starttime**.

Message **!starting** when the raid is beginning to clear the raid's 'here' list.

This channel will be deleted five minutes after the timer expires.""").format(pokemon=raid.mention, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
    raidmessage = await Meowth.send_message(raid_channel, content = raidmsg, embed=raid_embed)

    server_dict[message.server.id]['raidchannel_dict'][raid_channel.id] = {
        'reportcity' : message.channel.id,
        'trainer_dict' : {},
        'exp' : time.time() + 60 * raid_info["raid_eggs"][get_level(entered_raid)]['raidtime'], # minutes from now
        'manual_timer' : False, # No one has explicitly set the timer, Meowth is just assuming 2 hours
        'active' : True,
        'raidmessage' : raidmessage.id,
        'raidreport' : raidreport.id,
        'address' : raid_details,
        'type' : 'raid',
        'pokemon' : entered_raid,
        'egglevel' : '0',
        'gymhuntrgps' : gymhuntrgps
        }

    if raidexp is not False:
        await _timerset(raid_channel,raidexp)
    else:
        #await _timerset(raid_channel, raid_info["raid_eggs"][get_level(entered_raid)]['raidtime'])
        #server_dict[message.server.id]['raidchannel_dict'][raid_channel.id]['manual_timer'] = False
        await Meowth.send_message(raid_channel, content = _("Meowth! Hey {member}, if you can, set the time left on the raid using **!timerset <minutes>** so others can check it with **!timer**.").format(member=message.author.mention))
    if huntr:
        await Meowth.send_message(raid_channel, "This raid was reported by GymHuntrBot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
    event_loop.create_task(expiry_check(raid_channel))

# Print raid timer
async def print_raid_timer(channel):
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[channel.server.id]['offset'])
    end = now + datetime.timedelta(seconds=server_dict[channel.server.id]['raidchannel_dict'][channel.id]['exp']-time.time())
    timerstr = " "
    if server_dict[channel.server.id]['raidchannel_dict'][channel.id]['type'] == 'egg':
        raidtype = "egg"
        raidaction = "hatch"
    else:
        raidtype = "raid"
        raidaction = "end"
    if not server_dict[channel.server.id]['raidchannel_dict'][channel.id]['active']:
        timerstr += _("This {raidtype}'s timer has already expired as of {expiry_time}!").format(raidtype=raidtype,expiry_time=end.strftime("%I:%M %p (%H:%M)"))
    else:
        if server_dict[channel.server.id]['raidchannel_dict'][channel.id]['egglevel'] == "EX" or server_dict[channel.server.id]['raidchannel_dict'][channel.id]['type'] == "exraid":
            if server_dict[channel.server.id]['raidchannel_dict'][channel.id]['manual_timer']:
                timerstr += _("This {raidtype} will {raidaction} on {expiry}!").format(raidtype=raidtype,raidaction=raidaction,expiry=end.strftime("%B %d at %I:%M %p (%H:%M)"))
            else:
                timerstr += _("No one told me when the {raidtype} will {raidaction}, so I'm assuming it will {raidaction} on {expiry}!").format(raidtype=raidtype,raidaction=raidaction,expiry=end.strftime("%B %d at %I:%M %p (%H:%M)"))
        else:
            if server_dict[channel.server.id]['raidchannel_dict'][channel.id]['manual_timer']:
                timerstr += _("This {raidtype} will {raidaction} at {expiry_time}!").format(raidtype=raidtype,raidaction=raidaction,expiry_time=end.strftime("%I:%M %p (%H:%M)"))
            else:
                timerstr += _("No one told me when the {raidtype} will {raidaction}, so I'm assuming it will {raidaction} at {expiry_time}!").format(raidtype=raidtype,raidaction=raidaction,expiry_time=end.strftime("%I:%M %p (%H:%M)"))

    return timerstr



@Meowth.command(pass_context=True)
@checks.raidchannel()
async def timerset(ctx,timer):
    """Set the remaining duration on a raid.

    Usage: !timerset <minutes>
    Works only in raid channels, can be set or overridden by anyone.
    Meowth displays the end time in HH:MM local time."""
    message = ctx.message
    channel = message.channel
    server = message.server
    if not checks.check_exraidchannel(ctx):
        if server_dict[server.id]['raidchannel_dict'][channel.id]['type'] == 'egg':
            raidlevel = server_dict[server.id]['raidchannel_dict'][channel.id]['egglevel']
            raidtype = "Raid Egg"
            maxtime = raid_info["raid_eggs"][raidlevel]['hatchtime']
        else:
            raidlevel = get_level(server_dict[server.id]['raidchannel_dict'][channel.id]['pokemon'])
            raidtype = "Raid"
            maxtime = raid_info["raid_eggs"][raidlevel]['raidtime']
        if timer.isdigit():
            raidexp = int(timer)
        elif ":" in timer:
            h,m = re.sub(r"[a-zA-Z]", "", timer).split(":",maxsplit=1)
            if h is "": h = "0"
            if m is "": m = "0"
            if h.isdigit() and m.isdigit():
                raidexp = 60 * int(h) + int(m)
            else:
                await Meowth.send_message(channel, "Meowth! I couldn't understand your time format. Try again like this: **!timerset <minutes>**")
                return
        else:
            await Meowth.send_message(channel, "Meowth! I couldn't understand your time format. Try again like this: **!timerset <minutes>**")
            return
        if _timercheck(raidexp, maxtime):
            await Meowth.send_message(channel, _("Meowth...that's too long. Level {raidlevel} {raidtype}s currently last no more than {maxtime} minutes...").format(raidlevel=str(raidlevel),raidtype=raidtype.capitalize(), maxtime=str(maxtime)))
            return
        await _timerset(channel, raidexp)

    if checks.check_exraidchannel(ctx):
        if checks.check_eggchannel(ctx):
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[channel.server.id]['offset'])
            timer_split = message.clean_content.lower().split()
            del timer_split[0]
            try:
                start = datetime.datetime.strptime(" ".join(timer_split)+" "+str(now.year), '%m/%d %I:%M %p %Y')
                if start.month < now.month:
                    start = start.replace(year=now.year+1)
            except ValueError:
                await Meowth.send_message(channel, _("Meowth! Your timer wasn't formatted correctly. Change your **!timerset** to match this format: **MM/DD HH:MM AM/PM**"))
                return
            diff = start - now
            total = (diff.total_seconds() / 60)
            if now <= start:
                await _timerset(channel, total)
            elif now > start:
                await Meowth.send_message(channel, _("Meowth! Please enter a time in the future."))
        else:
            await Meowth.send_message(channel, _("Meowth! Timerset isn't supported for EX Raids after they have hatched."))

def _timercheck(time, maxtime):
    return time > maxtime

async def _timerset(raidchannel, exptime):
    server = raidchannel.server
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[server.id]['offset'])
    end = now + datetime.timedelta(minutes=exptime)
    # Update timestamp
    server_dict[server.id]['raidchannel_dict'][raidchannel.id]['exp'] = time.time() + (exptime * 60)
    # Reactivate channel
    if not server_dict[server.id]['raidchannel_dict'][raidchannel.id]['active']:
        await Meowth.send_message(raidchannel, "The channel has been reactivated.")
    server_dict[server.id]['raidchannel_dict'][raidchannel.id]['active'] = True
    # Mark that timer has been manually set
    server_dict[server.id]['raidchannel_dict'][raidchannel.id]['manual_timer'] = True
    # Send message
    timerstr = await print_raid_timer(raidchannel)
    await Meowth.send_message(raidchannel, timerstr)
    # Edit topic
    topicstr = ""
    if server_dict[server.id]['raidchannel_dict'][raidchannel.id]['type'] == "egg":
        egglevel = server_dict[server.id]['raidchannel_dict'][raidchannel.id]['egglevel']
        hatch = end
        end = hatch + datetime.timedelta(minutes=raid_info["raid_eggs"][egglevel]['raidtime'])
        topicstr += _("Hatches on {expiry}").format(expiry=hatch.strftime("%B %d at %I:%M %p (%H:%M) | "))
        topicstr += _("Ends on {end}").format(end=end.strftime("%B %d at %I:%M %p (%H:%M)"))
    else:
        topicstr += _("Ends on {end}").format(end=end.strftime("%B %d at %I:%M %p (%H:%M)"))
    await Meowth.edit_channel(raidchannel, topic=topicstr)
    raidchannel = Meowth.get_channel(raidchannel.id)
    # Trigger expiry checking
    event_loop.create_task(expiry_check(raidchannel))

@Meowth.command(pass_context=True)
@checks.raidchannel()
async def timer(ctx):
    """Have Meowth resend the expire time message for a raid.

    Usage: !timer
    The expiry time should have been previously set with !timerset."""
    timerstr = "Meowth!"
    timerstr += await print_raid_timer(ctx.message.channel)
    await Meowth.send_message(ctx.message.channel, timerstr)

"""
Behind-the-scenes functions for raid management.
Triggerable through commands or through emoji
"""
async def _maybe(message, count):
    trainer_dict = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']
    if count == 1:
        await Meowth.send_message(message.channel, _("Meowth! {member} is interested!").format(member=message.author.mention))
    else:
        await Meowth.send_message(message.channel, _("Meowth! {member} is interested with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.id not in server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']:
        trainer_dict[message.author.id] = {}
    trainer_dict[message.author.id]['status'] = "maybe"
    trainer_dict[message.author.id]['count'] = count
    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'] = trainer_dict

async def _coming(message, count):
    trainer_dict = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']

    if count == 1:
        await Meowth.send_message(message.channel, _("Meowth! {member} is on the way!").format(member=message.author.mention))
    else:
        await Meowth.send_message(message.channel, _("Meowth! {member} is on the way with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.id not in trainer_dict:
        trainer_dict[message.author.id] = {}
    trainer_dict[message.author.id]['status'] = "omw"
    trainer_dict[message.author.id]['count'] = count
    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'] = trainer_dict


async def _here(message, count):
    trainer_dict = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']
    lobbymsg = ""
    try:
        if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['lobby']:
            lobbymsg += " There is a group already in the lobby! Use **!lobby** to join them or **!backout** to request a backout! Otherwise, you may be stuck waiting for the next group!"
    except KeyError:
        pass
    if count == 1:
        await Meowth.send_message(message.channel, _("Meowth! {member} is at the raid!"+lobbymsg).format(member=message.author.mention))
    else:
        await Meowth.send_message(message.channel, _("Meowth! {member} is at the raid with a total of {trainer_count} trainers!"+lobbymsg).format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.id not in trainer_dict:
        trainer_dict[message.author.id] = {}
    trainer_dict[message.author.id]['status'] = "waiting"
    trainer_dict[message.author.id]['count'] = count
    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'] = trainer_dict

async def _lobby(message, count):
    if 'lobby' not in server_dict[message.server.id]['raidchannel_dict'][message.channel.id]:
        await Meowth.send_message(message.channel, "Meowth! There is no group in the lobby for you to join! Use **!starting** if the group waiting at the raid is entering the lobby!")
        return
    trainer_dict = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']
    if count == 1:
        await Meowth.send_message(message.channel, _("Meowth! {member} is entering the lobby!").format(member=message.author.mention))
    else:
        await Meowth.send_message(message.channel, _("Meowth! {member} is entering the lobby with a total of {trainer_count} trainers!").format(member=message.author.mention, trainer_count=count))
    # Add trainer name to trainer list
    if message.author.id not in trainer_dict:
        trainer_dict[message.author.id] = {}
    trainer_dict[message.author.id]['status'] = "lobby"
    trainer_dict[message.author.id]['count'] = count
    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'] = trainer_dict

async def _cancel(message):
    author = message.author
    channel = message.channel
    server = message.server
    try:
        t_dict = server_dict[server.id]['raidchannel_dict'][channel.id]['trainer_dict'][author.id]
    except KeyError:
        await Meowth.send_message(channel, _("Meowth! {member} has no status to cancel!").format(member=author.mention))
        return

    if t_dict['status'] == "maybe":
        if t_dict['count'] == 1:
            await Meowth.send_message(channel, _("Meowth! {member} is no longer interested!").format(member=author.mention))
        else:
            await Meowth.send_message(channel, _("Meowth! {member} and their total of {trainer_count} trainers are no longer interested!").format(member=author.mention, trainer_count=t_dict['count']))
    if t_dict['status'] == "waiting":
        if t_dict['count'] == 1:
            await Meowth.send_message(channel, _("Meowth! {member} has left the raid!").format(member=author.mention))
        else:
            await Meowth.send_message(channel, _("Meowth! {member} and their total of {trainer_count} trainers have left the raid!").format(member=author.mention, trainer_count=t_dict['count']))
    if t_dict['status'] == "omw":
        if t_dict['count'] == 1:
            await Meowth.send_message(channel, _("Meowth! {member} is no longer on their way!").format(member=author.mention))
        else:
            await Meowth.send_message(channel, _("Meowth! {member} and their total of {trainer_count} trainers are no longer on their way!").format(member=author.mention, trainer_count=t_dict['count']))
    if t_dict['status'] == "lobby":
        if t_dict['count'] == 1:
            await Meowth.send_message(channel, "Meowth! {member} has backed out of the lobby!".format(member=author.mention))
        else:
            await Meowth.send_message(channel, "Meowth! {member} and their total of {trainer_count} trainers have backed out of the lobby!".format(member=author.mention, trainer_count=t_dict['count']))
    t_dict['status'] = None
    t_dict['count'] = 1

@Meowth.event
async def on_message(message):
    if str(message.author) == "GymHuntrBot#7279":
        if message.embeds:
            if len(message.embeds[0]['title'].split(" ")) == 5 and server_dict[message.server.id]['autoraid']:
                ghduplicate = False
                ghraidlevel = message.embeds[0]['title'].split(" ")[1]
                ghgps = message.embeds[0]['url'].split("#")[1]
                ghdesc = message.embeds[0]['description'].splitlines()
                ghgym = ghdesc[0][2:-3]
                ghpokeid = ghdesc[1]
                ghmoves = "\u200b"
                if len(ghdesc[2].split()) > 3:
                    ghmoves = ghdesc[2].split("**Moves:** ")[1]
                ghtime = ghdesc[3].split(" ")
                ghhour = ghtime[2]
                ghminute = int(ghtime[4].zfill(2))
                huntr = "!raid {0} {1} {2}:{3}|{4}|{5}".format(ghpokeid, ghgym, ghhour, ghminute, ghgps, ghmoves)
                await Meowth.delete_message(message)
                for channelid in server_dict[message.server.id]['raidchannel_dict']:
                    try:
                        if server_dict[message.server.id]['raidchannel_dict'][channelid]['gymhuntrgps'] == ghgps:
                            ghduplicate = True
                            channel = Meowth.get_channel(channelid)
                            if server_dict[message.server.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                                await _eggtoraid(ghpokeid.lower(), channel, huntr)
                            await Meowth.send_message(channel, _("This {pokemon}'s moves are: **{moves}**").format(pokemon=ghpokeid, moves=ghmoves))
                            break
                    except KeyError:
                        pass
                if ghduplicate == False and int(ghraidlevel) in server_dict[message.server.id]['raidlvls']:
                    await _raid(message, huntr)
                elif ghduplicate is False and int(ghraidlevel) not in server_dict[message.server.id]['raidlvls']:
                    raid = discord.utils.get(message.server.roles, name = ghpokeid.lower())
                    if raid is None:
                        raid = await Meowth.create_role(server = message.server, name = ghpokeid.lower(), hoist = False, mentionable = True)
                    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the raid!"),url=_("https://www.google.com/maps/dir/Current+Location/{0}").format(ghgps),colour=message.server.me.colour)
                    raid_number = pkmn_info['pokemon_list'].index(ghpokeid.lower()) + 1
                    raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/pkmn/{0}_.png?cache=0".format(str(raid_number).zfill(3))
                    raid_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}\n{moves}").format(pokemon=ghpokeid.capitalize(),pokemonnumber=str(raid_number),type="".join(get_type(message.server, raid_number)),moves=ghmoves),inline=True)
                    raid_embed.add_field(name="**Weaknesses:**", value=_("{weakness_list}").format(weakness_list=weakness_to_str(message.server, get_weaknesses(ghpokeid.lower()))),inline=True)
                    raid_embed.add_field(name="**Location:**", value=_("{raid_details}").format(raid_details=ghgym),inline=True)
                    raid_embed.add_field(name="**Remaining:**", value=_("{minutes} mins").format(minutes=ghminute),inline=True)
                    raid_embed.set_thumbnail(url=raid_img_url)
                    raid_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
                    raidreport = await Meowth.send_message(message.channel, content = _("Meowth! {pokemon} raid reported by {member}! Details: {location_details}").format(pokemon=raid.mention, member=message.author.mention, location_details=ghgym),embed=raid_embed)
                    await asyncio.sleep(int(ghminute)*60)
                    expiremsg = _("**This {pokemon} raid has expired!**").format(pokemon=ghpokeid)
                    try:
                        await Meowth.edit_message(raidreport, embed=discord.Embed(description=expiremsg,colour=message.server.me.colour))
                    except discord.errors.NotFound:
                        pass
                return
            elif len(message.embeds[0]['title'].split(" ")) == 6 and server_dict[message.server.id]['autoegg']:
                ghduplicate = False
                ghgps = message.embeds[0]['url'].split("#")[1]
                ghegglevel = message.embeds[0]['title'].split(" ")[1]
                ghdesc = message.embeds[0]['description'].splitlines()
                ghgym = ghdesc[0][2:-3]
                ghtime = ghdesc[1].split(" ")
                ghhour = ghtime[2]
                ghminute = int(ghtime[4].zfill(2))
                huntr = "!raidegg {0} {1} {2}:{3}|{4}".format(ghegglevel, ghgym, ghhour, ghminute, ghgps)
                await Meowth.delete_message(message)
                for channelid in server_dict[message.server.id]['raidchannel_dict']:
                    try:
                        if server_dict[message.server.id]['raidchannel_dict'][channelid]['gymhuntrgps'] == ghgps:
                            ghduplicate = True
                            break
                    except KeyError:
                        pass
                if ghduplicate == False and int(ghegglevel) in server_dict[message.server.id]['egglvls']:
                    await _raidegg(message, huntr)
                elif ghduplicate is False and int(ghegglevel) not in server_dict[message.server.id]['egglvls']:
                    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the coming raid!"),url=_("https://www.google.com/maps/dir/Current+Location/{0}").format(ghgps),colour=message.server.me.colour)
                    raid_embed.add_field(name="**Location:**", value=_("{raid_details}").format(raid_details=ghgym),inline=True)
                    raid_embed.add_field(name="**Starting in:**", value=_("{minutes} mins").format(minutes=ghminute),inline=True)
                    raid_embed.set_thumbnail(url=_("https://raw.githubusercontent.com/doonce/Meowth/master/images/eggs/{}.png?cache=0".format(str(ghegglevel))))
                    raid_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
                    raidreport = await Meowth.send_message(message.channel, content = _("Meowth! Level {level} raid egg reported by {member}! Details: {location_details}.").format(level=ghegglevel, member=message.author.mention, location_details=ghgym),embed=raid_embed)
                    await asyncio.sleep(int(ghminute)*60)
                    expiremsg = _("**This level {level} raid egg has hatched!**").format(level=ghegglevel)
                    try:
                        await Meowth.edit_message(raidreport, embed=discord.Embed(description=expiremsg,colour=message.server.me.colour))
                    except discord.errors.NotFound:
                        pass
                return
            return
        return
    if str(message.author) == "HuntrBot#1845" and server_dict[message.server.id]['autowild']:
        if message.embeds:
            hlocation = message.embeds[0]['url'].split("#")[1]
            hpokeid = message.embeds[0]['title'].split(" ")[2]
            hdesc = message.embeds[0]['description'].splitlines()
            hexpire = hdesc[2].split(": ")[1][:-1]
            hweather = hdesc[3].split(": ")[1][1:-1]
            huntr = "!wild {0} {1}|{2}|{3}".format(hpokeid, hlocation, hexpire, hweather)
            await Meowth.delete_message(message)
            await _wild(message, huntr)
            return
        return
    if message.server is not None:
        raid_status = server_dict[message.server.id]['raidchannel_dict'].get(message.channel.id,None)
        if raid_status is not None:
            if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['active']:
                trainer_dict = server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict']
                if message.author.id in trainer_dict:
                    count = trainer_dict[message.author.id]['count']
                else:
                    count = 1
                omw_emoji = parse_emoji(message.server, config['omw_id'])
                if message.content.startswith(omw_emoji):
                    try:
                        if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['type'] == "egg":
                            if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['pokemon'] == "":
                                await Meowth.send_message(message.channel, _("Meowth! Please wait until the raid egg has hatched before announcing you're coming or present."))
                                return
                    except:
                        pass
                    emoji_count = message.content.count(omw_emoji)
                    await _coming(message, emoji_count)
                    return
                here_emoji = parse_emoji(message.server, config['here_id'])
                if message.content.startswith(here_emoji):
                    try:
                        if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['type'] == "egg":
                            if server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['pokemon'] == "":
                                await Meowth.send_message(message.channel, _("Meowth! Please wait until the raid egg has hatched before announcing you're coming or present."))
                                return
                    except:
                        pass
                    emoji_count = message.content.count(here_emoji)
                    await _here(message, emoji_count)
                    return
                if "/maps" in message.content:
                    mapsindex = message.content.find("/maps")
                    newlocindex = message.content.rfind("http", 0, mapsindex)
                    if newlocindex == -1:
                        return
                    newlocend = message.content.find(" ", newlocindex)
                    if newlocend == -1:
                        newloc = message.content[newlocindex:]
                    else:
                        newloc = message.content[newlocindex:newlocend+1]
                    oldraidmsg = await Meowth.get_message(message.channel, server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidmessage'])
                    report_channel = Meowth.get_channel(server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['reportcity'])
                    oldreportmsg = await Meowth.get_message(report_channel, server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidreport'])
                    oldembed = oldraidmsg.embeds[0]
                    newembed = discord.Embed(title=oldembed['title'],url=newloc,colour=message.server.me.colour)
                    newembed.add_field(name=oldembed['fields'][0]['name'],value=oldembed['fields'][0]['value'],inline=True)
                    newembed.add_field(name=oldembed['fields'][1]['name'],value=oldembed['fields'][1]['value'],inline=True)
                    newembed.set_footer(text=oldembed['footer']['text'], icon_url=oldembed['footer']['icon_url'])
                    newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
                    try:
                        newraidmsg = await Meowth.edit_message(oldraidmsg, new_content=oldraidmsg.content, embed=newembed)
                    except:
                        pass
                    try:
                        newreportmsg = await Meowth.edit_message(oldreportmsg, new_content=oldreportmsg.content, embed=newembed)
                    except:
                        pass
                    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidmessage'] = newraidmsg.id
                    server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidreport'] = newreportmsg.id
                    otw_list = []
                    trainer_dict = copy.deepcopy(server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'])
                    for trainer in trainer_dict.keys():
                        if trainer_dict[trainer]['status']=='omw':
                            user = message.server.get_member(trainer)
                            otw_list.append(user.mention)
                    await Meowth.send_message(message.channel, content = _("Meowth! Someone has suggested a different location for the raid! Trainers {trainer_list}: make sure you are headed to the right place!").format(trainer_list=", ".join(otw_list)), embed = newembed)
                    return

    if message.content.startswith(_get_prefix(Meowth, message)):
        messagelist = message.content.split(" ")
        firstsplit = re.split("\n|\r", messagelist.pop(0))
        command = firstsplit.pop(0).lower()
        message.content = command + "\n" + "\n".join(firstsplit) + " " + " ".join(messagelist)
    await Meowth.process_commands(message)

@Meowth.command(pass_context=True)
@checks.cityexraidchannel()
@checks.raidset()
async def exraid(ctx):
    """Report an upcoming EX raid.

    Usage: !exraid <location>
    Meowth will insert the details (really just everything after the species name) into a
    Google maps link and post the link to the same channel the report was made in.
    Meowth's message will also include the type weaknesses of the boss.

    Finally, Meowth will create a separate channel for the raid report, for the purposes of organizing the raid."""
    await _exraid(ctx)

async def _exraid(ctx):
    message = ctx.message
    channel = message.channel
    fromegg = False
    exraid_split = message.clean_content.lower().split()
    del exraid_split[0]
    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", exraid_split[0])), None)
    if pkmn_match:
        del exraid_split[0]
    if len(exraid_split) <= 0:
        await Meowth.send_message(channel, _("Meowth! Give more details when reporting! Usage: **!exraid <location>**"))
        return
    raid_details = " ".join(exraid_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Meowth.send_message(channel, _("Meowth! Give more details when reporting! Usage: **!exraid <location>**"))
        return

    raid_gmaps_link = create_gmaps_query(raid_details, message.channel)

    egg_info = raid_info['raid_eggs']['EX']
    egg_img = egg_info['egg_img']
    boss_list = []
    for p in egg_info['pokemon']:
        p_name = get_name(p)
        p_type = get_type(message.server,p)
        boss_list.append(p_name+" ("+str(p)+") "+''.join(p_type))
    raid_channel_name = "ex-raid-egg-" + sanitize_channel_name(raid_details)
    raid_channel_overwrites = channel.overwrites
    meowth_overwrite = (Meowth.user, discord.PermissionOverwrite(send_messages = True))
    for overwrite in raid_channel_overwrites:
        if isinstance(overwrite[0], discord.Role):
            if overwrite[0].permissions.manage_server:
                continue
        overwrite[1].send_messages = False
    raid_channel = await Meowth.create_channel(message.server, raid_channel_name, *raid_channel_overwrites, meowth_overwrite)
    raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/eggs/{}?cache=0".format(str(egg_img))
    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the coming raid!"),url=raid_gmaps_link,colour=message.server.me.colour)
    if len(egg_info['pokemon']) > 1:
        raid_embed.add_field(name="**Possible Bosses:**", value=_("{bosslist1}").format(bosslist1="\n".join(boss_list[::2])), inline=True)
        raid_embed.add_field(name="\u200b", value=_("{bosslist2}").format(bosslist2="\n".join(boss_list[1::2])), inline=True)
    else:
        raid_embed.add_field(name="**Possible Bosses:**", value=_("{bosslist}").format(bosslist="".join(boss_list)), inline=True)
        raid_embed.add_field(name="\u200b", value="\u200b", inline=True)
    raid_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
    raid_embed.set_thumbnail(url=raid_img_url)
    raidreport = await Meowth.send_message(channel, content = _("Meowth! EX raid egg reported by {member}! Details: {location_details}. Use the **!invite** command to gain access and coordinate in {raid_channel}").format(member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention),embed=raid_embed)
    await asyncio.sleep(1) #Wait for the channel to be created.

    raidmsg = _("""Meowth! EX raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here after using **!invite** to gain access!

To update your status, choose from the following commands: **!maybe**, **!coming**, **!here**, **!cancel**. If you are bringing more than one trainer/account, add in the number of accounts total on your first status update.
Example: `!coming 5`

To see the list of trainers who have given their status:
**!list interested**, **!list coming**, **!list here** or use just **!list** to see all lists. Use **!list teams** to see team distribution.

Sometimes I'm not great at directions, but I'll correct my directions if anybody sends me a maps link or uses **!location new <address>**. You can see the location of a raid by using **!location**

You can set the start time with **!starttime [HH:MM AM/PM]** and access this with **!starttime**.

Message **!starting** when the raid is beginning to clear the raid's 'here' list.""").format(member=message.author.mention, citychannel=channel.mention, location_details=raid_details)
    raidmessage = await Meowth.send_message(raid_channel, content = raidmsg, embed=raid_embed)

    server_dict[message.server.id]['raidchannel_dict'][raid_channel.id] = {
        'reportcity' : channel.id,
        'trainer_dict' : {},
        'exp' : time.time() + 60*60*24*raid_info['raid_eggs']['EX']['hatchtime'], # days from now
        'manual_timer' : False,
        'active' : True,
        'raidmessage' : raidmessage.id,
        'raidreport' : raidreport.id,
        'address' : raid_details,
        'type' : 'egg',
        'pokemon' : '',
        'egglevel' : 'EX',
        'gymhuntrgps' : False
        }

    if len(raid_info['raid_eggs']['EX']['pokemon']) == 1:
        await _eggassume("assume "+ get_name(raid_info['raid_eggs']['EX']['pokemon'][0]), raid_channel)
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[raid_channel.server.id]['offset'])
    await Meowth.send_message(raid_channel, content = _("Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <date and time>** so others can check it with **!timer**. **<date and time>** should look like this **{format}**, but set it to the date and time your invitation has.").format(member=message.author.mention, format=now.strftime('%m/%d %I:%M %p')))
    event_loop.create_task(expiry_check(raid_channel))

@Meowth.command(pass_context=True)
@checks.citychannel()
@checks.raidset()
async def raidegg(ctx):
    """Report a raid egg.

    Usage: !raidegg <level> <location> [minutes]

    Meowth will give a map link to the entered location and create a channel for organising the coming raid in.
    Meowth will also provide info on the possible bosses that can hatch and their types.

    <level> - Required. Level of the egg. Levels are from 1 to 5.
    <location> - Required. Address/Location of the gym.
    <minutes-remaining> - Not required. Time remaining until the egg hatches into an open raid. 1-60 minutes will be accepted. If not provided, 1 hour is assumed. Whole numbers only."""
    huntr = False
    await _raidegg(ctx.message, huntr)

async def _raidegg(message, huntr):
    if not huntr:
        raidegg_split = message.clean_content.lower().split()
        gymhuntrgps = False
    else:
        raidegg_split = huntr.split("|")[0].lower().split()
        gymhuntrgps = huntr.split("|")[1]
    del raidegg_split[0]
    if raidegg_split[0] == "egg":
        del raidegg_split[0]
    if len(raidegg_split) <= 1:
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Usage: **!raidegg <level> <location>**"))
        return

    if raidegg_split[0].isdigit():
        egg_level = int(raidegg_split[0])
        del raidegg_split[0]
    else:
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info."))
        return

    if raidegg_split[-1].isdigit():
        raidexp = int(raidegg_split[-1])
        del raidegg_split[-1]
    elif ":" in raidegg_split[-1]:
        raidegg_split[-1] = re.sub(r"[a-zA-Z]", "", raidegg_split[-1])
        if raidegg_split[-1].split(":")[0] == "":
            endhours = 0
        else:
            endhours = int(raidegg_split[-1].split(":")[0])
        if raidegg_split[-1].split(":")[1] == "":
            endmins = 0
        else:
            endmins = int(raidegg_split[-1].split(":")[1])
        raidexp = 60 * endhours + endmins
        del raidegg_split[-1]
    else:
        raidexp = False

    if raidexp and not huntr:
        if _timercheck(raidexp, raid_info["raid_eggs"][str(egg_level)]['hatchtime']):
            await Meowth.send_message(message.channel, _("Meowth...that's too long. Level {raidlevel} Raid Eggs currently last no more than {hatchtime} minutes...").format(raidlevel=egg_level,hatchtime=raid_info["raid_eggs"][str(egg_level)]['hatchtime']))
            return

    raid_details = " ".join(raidegg_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await Meowth.send_message(message.channel, _("Meowth! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info."))
        return

    if not huntr:
        raid_gmaps_link = create_gmaps_query(raid_details, message.channel)
    else:
        raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(huntr.split("|")[1])

    if egg_level > 5 or egg_level == 0:
        await Meowth.send_message(message.channel, _("Meowth! Raid egg levels are only from 1-5!"))
        return
    else:
        egg_level = str(egg_level)
        egg_info = raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_list = []
        for p in egg_info['pokemon']:
            p_name = get_name(p)
            p_type = get_type(message.server,p)
            boss_list.append(p_name+" ("+str(p)+") "+''.join(p_type))
        raid_channel_name = "level-" + egg_level + "-egg-" + sanitize_channel_name(raid_details)
        raid_channel = await Meowth.create_channel(message.server, raid_channel_name, *message.channel.overwrites)
        raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/eggs/{}?cache=0".format(str(egg_img))
        raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the coming raid!"),url=raid_gmaps_link,colour=message.server.me.colour)
        if len(egg_info['pokemon']) > 1:
            raid_embed.add_field(name="**Possible Bosses:**", value=_("{bosslist1}").format(bosslist1="\n".join(boss_list[::2])), inline=True)
            raid_embed.add_field(name="\u200b", value=_("{bosslist2}").format(bosslist2="\n".join(boss_list[1::2])), inline=True)
        else:
            raid_embed.add_field(name="**Possible Bosses:**", value=_("{bosslist}").format(bosslist="".join(boss_list)), inline=True)
            raid_embed.add_field(name="\u200b", value="\u200b", inline=True)
        if huntr:
            raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
        raid_embed.set_footer(text=_("Reported by @{author}").format(author=message.author.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=message.author, format="jpg", size=32)))
        raid_embed.set_thumbnail(url=raid_img_url)
        raidreport = await Meowth.send_message(message.channel, content = _("Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}").format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention),embed=raid_embed)
        await asyncio.sleep(1) #Wait for the channel to be created.

        raidmsg = _("""Meowth! Level {level} raid egg reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!

Message **!maybe** if you're interested in attending. If you are bringing more than one trainer/account, add in the number at the end of the command.
Example: `!maybe 5`

Use **!list interested** to see the list of trainers who are interested or use just **!list** to see all lists. Use **!list teams** to see team distribution.

Sometimes I'm not great at directions, but I'll correct my directions if anybody sends me a maps link or uses **!location new <address>**. You can see the location of a raid by using **!location**

You can set the time until hatch with **!timerset <minutes>** and access this with **!timer**.
You can set the start time with **!starttime [HH:MM AM/PM]** and access this with **!starttime**.

Message **!raid <pokemon>** to update this channel into an open raid.
Message **!raid assume <pokemon>** to have the channel auto-update into an open raid.

When this egg raid expires, there will be 15 minutes to update it into an open raid before it'll be deleted.""").format(level=egg_level, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
        raidmessage = await Meowth.send_message(raid_channel, content = raidmsg, embed=raid_embed)
        server_dict[message.server.id]['raidchannel_dict'][raid_channel.id] = {
            'reportcity' : message.channel.id,
            'trainer_dict' : {},
            'exp' : time.time() + 60 * raid_info["raid_eggs"][egg_level]['hatchtime'], # minutes from now
            'manual_timer' : False, # No one has explicitly set the timer, Meowth is just assuming 2 hours
            'active' : True,
            'raidmessage' : raidmessage.id,
            'raidreport' : raidreport.id,
            'address' : raid_details,
            'type' : 'egg',
            'pokemon' : '',
            'egglevel' : egg_level,
            'gymhuntrgps' : gymhuntrgps
            }

        if raidexp is not False:
            await _timerset(raid_channel,raidexp)
        else:
            await _timerset(raid_channel, raid_info["raid_eggs"][egg_level]['hatchtime'])
            server_dict[message.server.id]['raidchannel_dict'][raid_channel.id]['manual_timer'] = False
            await Meowth.send_message(raid_channel, content = _("Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.").format(member=message.author.mention))
        if huntr:
            await Meowth.send_message(raid_channel, "This egg was reported by GymHuntrBot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
        if len(raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            await _eggassume("assume "+ get_name(raid_info['raid_eggs'][egg_level]['pokemon'][0]), raid_channel)
        event_loop.create_task(expiry_check(raid_channel))


async def _eggassume(args, raid_channel):
    eggdetails = server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id]
    egglevel = eggdetails['egglevel']
    manual_timer = eggdetails['manual_timer']
    report_channel = Meowth.get_channel(eggdetails['reportcity'])
    egg_report = await Meowth.get_message(report_channel, eggdetails['raidreport'])
    raid_message = await Meowth.get_message(raid_channel, eggdetails['raidmessage'])
    try:
        raid_messageauthor = raid_message.mentions[0]
    except IndexError:
        raid_messageauthor = "<@"+raid_message.raw_mentions[0]+">"
        logger.info("Hatching Mention Failed - Trying alternative method: channel: {} (id: {}) - server: {} | Attempted mention: {}...".format(raid_channel.name,raid_channel.id,raid_channel.server.name,raid_message.content[:125]))
    gymhuntrgps = eggdetails['gymhuntrgps']

    entered_raid = re.sub("[\@]", "", args.lstrip("assume").lstrip(" ").lower())
    entered_raid = get_name(entered_raid).lower() if entered_raid.isdigit() else entered_raid
    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_raid)), None)
    if pkmn_match:
        entered_raid = pkmn_match
    else:
        await Meowth.send_message(raid_channel, spellcheck(entered_raid))
        return
    raid_match = True if entered_raid in get_raidlist() else False
    if not raid_match:
        await Meowth.send_message(raid_channel, _("Meowth! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
        return
    else:
        if get_number(entered_raid) not in raid_info['raid_eggs'][egglevel]['pokemon']:
            await Meowth.send_message(raid_channel, _("Meowth! The Pokemon {pokemon} does not hatch from level {level} raid eggs!").format(pokemon=entered_raid.capitalize(), level=egglevel))
            return
    eggdetails['pokemon'] = entered_raid
    oldembed = raid_message.embeds[0]
    raid_gmaps_link = oldembed['url']
    raidrole = discord.utils.get(raid_channel.server.roles, name = entered_raid)
    if raidrole is None:
        raidrole = await Meowth.create_role(server = raid_channel.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/pkmn/{0}_.png?cache=0".format(str(raid_number).zfill(3))
    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the coming raid!"),url=raid_gmaps_link,colour=raid_channel.server.me.colour)
    raid_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}").format(pokemon=entered_raid.capitalize(),pokemonnumber=str(raid_number),type="".join(get_type(raid_channel.server, raid_number)),inline=True))
    raid_embed.add_field(name="**Weaknesses:**", value=_("{weakness_list}").format(weakness_list=weakness_to_str(raid_channel.server, get_weaknesses(entered_raid))),inline=True)
    if gymhuntrgps:
        raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
    raid_embed.set_footer(text=_("Reported by @{author}").format(author=raid_messageauthor.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=raid_messageauthor, format="jpg", size=32)))
    raid_embed.set_thumbnail(url=oldembed['thumbnail']['url'])

    try:
        raid_message = await Meowth.edit_message(raid_message, new_content=raid_message.content, embed=raid_embed)
    except discord.errors.NotFound:
        pass
    try:
        egg_report = await Meowth.edit_message(egg_report, new_content=egg_report.content, embed=raid_embed)
    except discord.errors.NotFound:
        pass
    await Meowth.send_message(raid_channel, _("Meowth! This egg will be assumed to be {pokemon} when it hatches!").format(pokemon=raidrole.mention))
    server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id] = eggdetails
    return

async def _eggtoraid(entered_raid, raid_channel, huntr):
    eggdetails = server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id]
    egglevel = eggdetails['egglevel']
    reportcitychannel = Meowth.get_channel(eggdetails['reportcity'])
    reportcity = reportcitychannel.name
    manual_timer = eggdetails['manual_timer']
    trainer_dict = eggdetails['trainer_dict']
    egg_address = eggdetails['address']
    egg_report = await Meowth.get_message(reportcitychannel, eggdetails['raidreport'])
    raid_message = await Meowth.get_message(raid_channel, eggdetails['raidmessage'])
    try:
        starttime = eggdetails['starttime']
    except KeyError:
        starttime = None
    try:
        raid_messageauthor = raid_message.mentions[0]
    except IndexError:
        raid_messageauthor = "<@"+raid_message.raw_mentions[0]+">"
        logger.info("Hatching Mention Failed - Trying alternative method: channel: {} (id: {}) - server: {} | Attempted mention: {}...".format(raid_channel.name,raid_channel.id,raid_channel.server.name,raid_message.content[:125]))
    gymhuntrgps = eggdetails['gymhuntrgps']
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[raid_channel.server.id]['offset'])
    end = now + datetime.timedelta(minutes=raid_info["raid_eggs"][egglevel]['raidtime'])
    raidexp = eggdetails['exp'] + 60 * raid_info['raid_eggs'][egglevel]['raidtime']

    if egglevel.isdigit():
        hatchtype = "raid"
        raidreportcontent = _("Meowth! The egg has hatched into a {pokemon} raid! Details: {location_details}. Coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), location_details=egg_address, raid_channel=raid_channel.mention)
        raidmsg = _("""Meowth! The egg reported by {member} in {citychannel} hatched into a {pokemon} raid! Details: {location_details}. Coordinate here!

To update your status, choose from the following commands: **!maybe**, **!coming**, **!here**, **!cancel**. If you are bringing more than one trainer/account, add in the number of accounts total on your first status update.
Example: `!coming 5`

To see the list of trainers who have given their status:
**!list interested**, **!list coming**, **!list here** or use just **!list** to see all lists. Use **!list teams** to see team distribution.

Sometimes I'm not great at directions, but I'll correct my directions if anybody sends me a maps link or uses **!location new <address>**. You can see the location of a raid by using **!location**

You can set the time remaining with **!timerset <minutes>** and access this with **!timer**.
You can set the start time with **!starttime [HH:MM AM/PM]** and access this with **!starttime**.

Message **!starting** when the raid is beginning to clear the raid's 'here' list.""").format(member= raid_messageauthor.mention, citychannel=reportcitychannel.mention, pokemon=entered_raid.capitalize(), location_details=egg_address)
    elif egglevel == "EX":
        hatchtype = "exraid"
        raidreportcontent = _("Meowth! The EX egg has hatched into a {pokemon} raid! Details: {location_details}. Use the **!invite** command to gain access and coordinate in {raid_channel}").format(pokemon=entered_raid.capitalize(), location_details=egg_address, raid_channel=raid_channel.mention)
        raidmsg = _("""Meowth! {pokemon} EX raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here after using **!invite** to gain access!

To update your status, choose from the following commands: **!maybe**, **!coming**, **!here**, **!cancel**. If you are bringing more than one trainer/account, add in the number of accounts total on your first status update.
Example: `!coming 5`

To see the list of trainers who have given their status:
**!list interested**, **!list coming**, **!list here** or use just **!list** to see all lists. Use **!list teams** to see team distribution.

Sometimes I'm not great at directions, but I'll correct my directions if anybody sends me a maps link or uses **!location new <address>**. You can see the location of a raid by using **!location**

You can set the start time with **!starttime [HH:MM AM/PM]** and access this with **!starttime**.

Message **!starting** when the raid is beginning to clear the raid's 'here' list.""").format(pokemon=entered_raid.capitalize(), member=raid_messageauthor.mention, citychannel=reportcitychannel.mention, location_details=egg_address)
    entered_raid = get_name(entered_raid).lower() if entered_raid.isdigit() else entered_raid
    rgx = r"[^a-zA-Z0-9]"
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, "", p) == re.sub(rgx, "", entered_raid)), None)
    if pkmn_match:
        entered_raid = pkmn_match
    else:
        await Meowth.send_message(raid_channel, spellcheck(entered_raid))
        return
    raid_match = True if entered_raid in get_raidlist() else False
    if not raid_match:
        await Meowth.send_message(raid_channel, _("Meowth! The Pokemon {pokemon} does not appear in raids!").format(pokemon=entered_raid.capitalize()))
        return
    else:
        if get_number(entered_raid) not in raid_info['raid_eggs'][egglevel]['pokemon']:
            await Meowth.send_message(raid_channel, _("Meowth! The Pokemon {pokemon} does not hatch from level {level} raid eggs!").format(pokemon=entered_raid.capitalize(), level=egglevel))
            return
    raid_channel_name = entered_raid + "-" + sanitize_channel_name(egg_address)
    oldembed = raid_message.embeds[0]
    raid_gmaps_link = oldembed['url']
    raid = discord.utils.get(raid_channel.server.roles, name = entered_raid)
    if raid is None:
        raid = await Meowth.create_role(server = raid_channel.server, name = entered_raid, hoist = False, mentionable = True)
        await asyncio.sleep(0.5)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = "https://raw.githubusercontent.com/doonce/Meowth/master/images/pkmn/{0}_.png?cache=0".format(str(raid_number).zfill(3))
    raid_embed = discord.Embed(title=_("Meowth! Click here for directions to the raid!"),url=raid_gmaps_link,colour=raid_channel.server.me.colour)
    raid_embed.add_field(name="**Details:**", value=_("{pokemon} ({pokemonnumber}) {type}").format(pokemon=entered_raid.capitalize(),pokemonnumber=str(raid_number),type="".join(get_type(raid_channel.server, raid_number)),inline=True))
    raid_embed.add_field(name="**Weaknesses:**", value=_("{weakness_list}").format(weakness_list=weakness_to_str(raid_channel.server, get_weaknesses(entered_raid))),inline=True)
    if gymhuntrgps:
        gymhuntrmoves = "\u200b"
        if huntr:
            gymhuntrmoves = huntr.split("|")[2]
        raid_embed.add_field(name=gymhuntrmoves, value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
    raid_embed.set_footer(text=_("Reported by @{author}").format(author=raid_messageauthor.display_name), icon_url=_("https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}".format(user=raid_messageauthor, format="jpg", size=32)))
    raid_embed.set_thumbnail(url=raid_img_url)
    await Meowth.edit_channel(raid_channel, name=raid_channel_name, topic=end.strftime("Ends on %B %d at %I:%M %p (%H:%M)"))
    try:
        raid_message = await Meowth.edit_message(raid_message, new_content=raidmsg, embed=raid_embed)
    except discord.errors.NotFound:
        pass
    try:
        egg_report = await Meowth.edit_message(egg_report, new_content=raidreportcontent, embed=raid_embed)
    except discord.errors.NotFound:
        pass
    server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id] = {
    'reportcity' : reportcitychannel.id,
    'trainer_dict' : trainer_dict,
    'exp' : raidexp,
    'manual_timer' : manual_timer,
    'active' : True,
    'raidmessage' : raid_message.id,
    'raidreport' : egg_report.id,
    'address' : egg_address,
    'type' : hatchtype,
    'pokemon' : entered_raid,
    'egglevel' : '0',
    'gymhuntrgps' : gymhuntrgps
    }
    if starttime:
        server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id]['starttime'] = starttime
    trainer_list = []
    trainer_dict = copy.deepcopy(server_dict[raid_channel.server.id]['raidchannel_dict'][raid_channel.id]['trainer_dict'])
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status'] =='maybe' or trainer_dict[trainer]['status'] =='omw' or trainer_dict[trainer]['status'] =='waiting':
            user = raid_channel.server.get_member(trainer)
            trainer_list.append(user.mention)
    await Meowth.send_message(raid_channel, content = _("Meowth! Trainers {trainer_list}: The raid egg has just hatched into a {pokemon} raid!\nIf you couldn't before, you're now able to update your status with **!coming** or **!here**. If you've changed your plans, use **!cancel**.").format(trainer_list=", ".join(trainer_list), pokemon=raid.mention), embed = raid_embed)
    event_loop.create_task(expiry_check(raid_channel))

@Meowth.command(pass_context=True,aliases=["i","maybe"])
@checks.activeraidchannel()
async def interested(ctx, *, count: str = None):
    """Indicate you are interested in the raid.

    Usage: !interested [message]
    Works only in raid channels. If message is omitted, assumes you are a group of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    trainer_dict = server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict']
    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Meowth.send_message(ctx.message.channel, _("Meowth! I can't understand how many are in your group. Just say **!interested** if you're by yourself, or **!interested 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.id in trainer_dict:
            count = trainer_dict[ctx.message.author.id]['count']
        else:
            count = 1

    await _maybe(ctx.message, count)


@Meowth.command(pass_context=True,aliases=["c"])
@checks.activeraidchannel()
async def coming(ctx, *, count: str = None):
    """Indicate you are on the way to a raid.

    Usage: !coming [message]
    Works only in raid channels. If message is omitted, checks for previous !maybe
    command and takes the count from that. If it finds none, assumes you are a group
    of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    try:
        if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['type'] == "egg":
            if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['pokemon'] == "":
                await Meowth.send_message(ctx.message.channel, _("Meowth! Please wait until the raid egg has hatched before announcing you're coming or present."))
                return
    except:
        pass

    trainer_dict = server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict']

    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Meowth.send_message(ctx.message.channel, _("Meowth! I can't understand how many are in your group. Just say **!coming** if you're by yourself, or **!coming 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.id in trainer_dict:
            count = trainer_dict[ctx.message.author.id]['count']
        else:
            count = 1

    await _coming(ctx.message, count)

@Meowth.command(pass_context=True,aliases=["h"])
@checks.activeraidchannel()
async def here(ctx, *, count: str = None):
    """Indicate you have arrived at the raid.

    Usage: !here [message]
    Works only in raid channels. If message is omitted, and
    you have previously issued !coming, then preserves the count
    from that command. Otherwise, assumes you are a group of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    try:
        if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['type'] == "egg":
            if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['pokemon'] == "":
                await Meowth.send_message(ctx.message.channel, _("Meowth! Please wait until the raid egg has hatched before announcing you're coming or present."))
                return
    except:
        pass

    trainer_dict = server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict']

    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Meowth.send_message(ctx.message.channel, _("Meowth! I can't understand how many are in your group. Just say **!here** if you're by yourself, or **!coming 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.id in trainer_dict:
            count = trainer_dict[ctx.message.author.id]['count']
        else:
            count = 1

    await _here(ctx.message, count)

@Meowth.command(pass_context=True,aliases=["l"])
@checks.activeraidchannel()
async def lobby(ctx, *, count: str = None):
    """Indicate you are entering the raid lobby.

    Usage: !lobby [message]
    Works only in raid channels. If message is omitted, and
    you have previously issued !coming, then preserves the count
    from that command. Otherwise, assumes you are a group of 1.
    Otherwise, this command expects at least one word in your message to be a number,
    and will assume you are a group with that many people."""
    try:
        if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['type'] == "egg":
            if server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['pokemon'] == "":
                await Meowth.send_message(ctx.message.channel, _("Meowth! Please wait until the raid egg has hatched before announcing you're coming or present."))
                return
    except:
        pass

    trainer_dict = server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict']

    if count:
        if count.isdigit():
            count = int(count)
        else:
            await Meowth.send_message(ctx.message.channel, _("Meowth! I can't understand how many are in your group. Just say **!here** if you're by yourself, or **!coming 5** for example if there are 5 in your group."))
            return
    else:
        if ctx.message.author.id in trainer_dict:
            count = trainer_dict[ctx.message.author.id]['count']
        else:
            count = 1

    await _lobby(ctx.message, count)

@Meowth.command(pass_context=True)
@checks.activeraidchannel()
async def cancel(ctx):
    """Indicate you are no longer interested in a raid.

    Usage: !cancel
    Works only in raid channels. Removes you and your party
    from the list of trainers who are "otw" or "here"."""
    await _cancel(ctx.message)

@Meowth.command(pass_context=True)
@checks.activeraidchannel()
async def starttime(ctx):
    """Set a time for a group to start a raid

    Usage: !starttime [HH:MM AM/PM]
    (You can also omit AM/PM and use 24-hour time!)
    Works only in raid channels. Sends a message and sets a group start time that
    can be seen using !starttime (without a time). One start time is allowed at
    a time and is visibile in !list output. Cleared with !starting."""
    message = ctx.message
    server = message.server
    channel = message.channel
    author = message.author
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[server.id]['offset'])
    start_split = message.clean_content.lower().split()
    rc_d = server_dict[server.id]['raidchannel_dict'][channel.id]
    if rc_d['type'] == "egg" and rc_d['egglevel'].isdigit():
        egglevel = rc_d['egglevel']
        mintime = (rc_d['exp'] - time.time())/60
        maxtime = mintime + raid_info['raid_eggs'][egglevel]['raidtime']
    elif rc_d['type'] == "raid":
        egglevel = get_level(rc_d['pokemon'])
        maxtime = (rc_d['exp'] - time.time())/60
    elif rc_d['type'] == "exraid" or rc_d['egglevel'] == "EX":
        egglevel = "EX"
        mintime = (rc_d['exp'] - time.time())/60
        maxtime = mintime  + raid_info['raid_eggs'][egglevel]['raidtime']
    del start_split[0]
    if len(start_split) > 0:
        try:
            alreadyset = rc_d['starttime']
        except KeyError:
            alreadyset = False
        if "am" in " ".join(start_split).lower() or "pm" in " ".join(start_split).lower():
            try:
                start = datetime.datetime.strptime(" ".join(start_split)+" "+str(now.month)+str(now.day)+str(now.year), '%I:%M %p %m%d%Y')
                if egglevel == "EX":
                    hatch = datetime.datetime.utcfromtimestamp(rc_d['exp']) + datetime.timedelta(hours=server_dict[server.id]['offset'])
                    start = start.replace(year=hatch.year, month=hatch.month, day=hatch.day)
            except ValueError:
                await Meowth.send_message(channel, _("Meowth! Your start time wasn't formatted correctly. Change your **!starttime** to match this format: **HH:MM AM/PM**"))
                return
        else:
            try:
                start = datetime.datetime.strptime(" ".join(start_split)+" "+str(now.month)+str(now.day)+str(now.year), '%H:%M %m%d%Y')
                if egglevel == "EX":
                    hatch = datetime.datetime.utcfromtimestamp(rc_d['exp']) + datetime.timedelta(hours=server_dict[server.id]['offset'])
                    start = start.replace(year=hatch.year, month=hatch.month, day=hatch.day)
            except ValueError:
                await Meowth.send_message(channel, _("Meowth! Your start time wasn't formatted correctly. Change your **!starttime** to match this format: **HH:MM AM/PM**"))
                return
        diff = start - now
        total = (diff.total_seconds() / 60)
        if total > maxtime:
            await Meowth.send_message(channel, _("Meowth! The raid will be over before that...."))
            return
        if total < mintime:
            await Meowth.send_message(channel, "Meowth! The egg will not hatch by then!")
            return
        if now > start:
            await Meowth.send_message(channel, _("Meowth! Please enter a time in the future."))
            return
        if alreadyset:
            rusure = await Meowth.send_message(channel,_("Meowth! There is already a start time of **{start}** set! Do you want to change it?").format(start=alreadyset.strftime("%I:%M %p (%H:%M)")))
            await asyncio.sleep(0.25)
            await Meowth.add_reaction(rusure,"✅") #checkmark
            await asyncio.sleep(0.25)
            await Meowth.add_reaction(rusure,"❎") #cross
            def check(react,user):
                if user.id != author.id:
                    return False
                return True
            res = await Meowth.wait_for_reaction(['✅','❎'], message=rusure, check=check, timeout=60)
            if res is not None:
                if res.reaction.emoji == "❎":
                    await Meowth.delete_message(rusure)
                    confirmation = await Meowth.send_message(channel,_("Start time change cancelled."))
                    await asyncio.sleep(10)
                    await Meowth.delete_message(confirmation)
                    return
                elif res.reaction.emoji == "✅":
                    await Meowth.delete_message(rusure)
                    if now <= start:
                        rc_d['starttime'] = start
                        await Meowth.send_message(channel, _("Meowth! The current start time has been set to: **{starttime}**").format(starttime=start.strftime("%I:%M %p (%H:%M)")))
                        return
        else:
            if now <= start:
                rc_d['starttime'] = start
                await Meowth.send_message(channel, _("Meowth! The current start time has been set to: **{starttime}**").format(starttime=start.strftime("%I:%M %p (%H:%M)")))
                return
    else:
        try:
            starttime = rc_d['starttime']
            if starttime < now:
                del rc_d['starttime']
                await Meowth.send_message(channel, _("Meowth! No start time has been set, set one with **!starttime HH:MM AM/PM**! (You can also omit AM/PM and use 24-hour time!)"))
                return
            await Meowth.send_message(channel, _("Meowth! The current start time is: **{starttime}**").format(starttime=starttime.strftime("%I:%M %p (%H:%M)")))
        except KeyError:
            await Meowth.send_message(channel, _("Meowth! No start time has been set, set one with **!starttime HH:MM AM/PM**! (You can also omit AM/PM and use 24-hour time!)"))

@Meowth.command(pass_context=True)
@checks.activeraidchannel()
async def starting(ctx):
    """Signal that a raid is starting.

    Usage: !starting
    Works only in raid channels. Sends a message and clears the waiting list. Users who are waiting
    for a second group must reannounce with the :here: emoji or !here."""

    ctx_startinglist = []
    id_startinglist = []

    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])

    # Add all waiting trainers to the starting list
    for trainer in trainer_dict:
        if trainer_dict[trainer]['status'] == "waiting":
            trainer_dict[trainer]['status'] =  "lobby"
            user = ctx.message.server.get_member(trainer)
            ctx_startinglist.append(user.mention)
            id_startinglist.append(trainer)

    # Go back and delete the trainers from the waiting list

    server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'] = trainer_dict
    try:
        starttime = server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['starttime']
        timestr = " to start at **{}** ".format(starttime.strftime("%I:%M %p (%H:%M)"))
        del server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['starttime']
    except KeyError:
        starttime = False
        timestr = " "
    starting_str = _("Meowth! The group that was waiting{timestr}is starting the raid! Trainers {trainer_list}, please respond with {here_emoji} or **!here** if you are waiting for another group!").format(timestr=timestr,trainer_list=", ".join(ctx_startinglist), here_emoji=parse_emoji(ctx.message.server, config['here_id']))
    server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['lobby'] = time.time() + 120
    if starttime:
        starting_str += "\n\nThe start time has also been cleared, new groups can set a new start time wtih **!starttime HH:MM AM/PM** (You can also omit AM/PM and use 24-hour time!)."
    if len(ctx_startinglist) == 0:
        starting_str = _("Meowth! How can you start when there's no one waiting at this raid!?")
    await Meowth.send_message(ctx.message.channel, starting_str)
    await asyncio.sleep(120)
    if 'lobby' not in server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id] or time.time() < server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id].get('lobby'):
        return
    ctx_lobbycount = 0
    trainer_delete_list = []
    for trainer in trainer_dict:
        if trainer_dict[trainer]['status'] == "lobby":
            ctx_lobbycount += trainer_dict[trainer]['count']
            trainer_delete_list.append(trainer)
    if ctx_lobbycount > 0:
        await Meowth.send_message(ctx.message.channel, "Meowth! The group of {count} in the lobby has entered the raid! Wish them luck!".format(count=str(ctx_lobbycount)))
    for trainer in trainer_delete_list:
        del trainer_dict[trainer]
    try:
        del server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['lobby']
    except KeyError:
        pass
    server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'] = trainer_dict

@Meowth.group(pass_context=True,aliases=["lists"])
@checks.cityraidchannel()
@checks.raidset()
async def list(ctx):
    """Lists all raid info for the current channel.

    Usage: !list
    Works only in raid or city channels. Calls the interested, waiting, and here lists. Also prints
    the raid timer. In city channels, lists all active raids."""

    if ctx.invoked_subcommand is None:
        listmsg = "**Meowth!** "
        server = ctx.message.server
        channel = ctx.message.channel
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[server.id]['offset'])
        if checks.check_citychannel(ctx):
            activeraidnum = 0
            cty = channel.name
            rc_d = server_dict[server.id]['raidchannel_dict']

            raid_dict = {}
            egg_dict = {}
            exraid_list = []
            for r in rc_d:
                reportcity = Meowth.get_channel(rc_d[r]['reportcity'])
                if reportcity.name == cty and rc_d[r]['active'] and discord.utils.get(server.channels, id=r):
                    exp = rc_d[r]['exp']
                    type = rc_d[r]['type']
                    level = rc_d[r]['egglevel']
                    if type == 'egg' and level.isdigit():
                        egg_dict[r] = exp
                    elif type == 'exraid' or level == "EX":
                        exraid_list.append(r)
                    else:
                        raid_dict[r] = exp

                    activeraidnum += 1

            def list_output(r):
                rchan = Meowth.get_channel(r)
                end = now + datetime.timedelta(seconds=rc_d[r]['exp']-time.time())
                output = ""
                start_str = ""
                ctx_waitingcount = 0
                ctx_omwcount = 0
                ctx_maybecount = 0
                ctx_lobbycount = 0
                for trainer in rc_d[r]['trainer_dict'].values():
                    if trainer['status'] == "waiting":
                        ctx_waitingcount += trainer['count']
                    elif trainer['status'] == "omw":
                        ctx_omwcount += trainer['count']
                    elif trainer['status'] == "maybe":
                        ctx_maybecount += trainer['count']
                    elif trainer['status'] == "lobby":
                        ctx_lobbycount += trainer['count']
                if rc_d[r]['manual_timer'] == False:
                    assumed_str = " (assumed)"
                else:
                    assumed_str = ""
                try:
                    starttime = rc_d[r]['starttime']
                    if starttime > now:
                        start_str = " Next group: **{}**".format(starttime.strftime("%I:%M %p (%H:%M)"))
                except KeyError:
                    starttime = False
                    pass
                if rc_d[r]['egglevel'].isdigit() and int(rc_d[r]['egglevel']) > 0:
                    expirytext = " - Hatches: {expiry}{is_assumed}".format(expiry=end.strftime("%I:%M %p (%H:%M)"), is_assumed=assumed_str)
                elif rc_d[r]['egglevel'] == "EX" or rc_d[r]['type'] == "exraid":
                    expirytext = " - Hatches: {expiry}{is_assumed}".format(expiry=end.strftime("%B %d at %I:%M %p (%H:%M)"),is_assumed=assumed_str)
                else:
                    expirytext = " - Expiry: {expiry}{is_assumed}".format(expiry=end.strftime("%I:%M %p (%H:%M)"), is_assumed=assumed_str)
                output += (_("    {raidchannel}{expiry_text}\n").format(raidchannel=rchan.mention, expiry_text=expirytext))
                output += (_("    {interestcount} interested, {comingcount} coming, {herecount} here, {lobbycount} in the lobby.{start_str}\n").format(raidchannel=rchan.mention, interestcount=ctx_maybecount, comingcount=ctx_omwcount, herecount=ctx_waitingcount, lobbycount=ctx_lobbycount, start_str=start_str))
                return output

            if activeraidnum:
                listmsg += (_("**Here's the current raids for {0}**\n\n").format(cty.capitalize()))

            if raid_dict:
                listmsg += (_("**Active Raids:**\n").format(cty.capitalize()))
                for r,e in sorted(raid_dict.items(), key=itemgetter(1)):
                    listmsg += list_output(r)
                listmsg += "\n"

            if egg_dict:
                listmsg += (_("**Raid Eggs:**\n").format(cty.capitalize()))
                for r,e in sorted(egg_dict.items(), key=itemgetter(1)):
                    listmsg += list_output(r)
                listmsg += "\n"

            if exraid_list:
                listmsg += (_("**EX Raids:**\n").format(cty.capitalize()))
                for r in exraid_list:
                    listmsg += list_output(r)

            if activeraidnum == 0:
                await Meowth.send_message(channel, _("Meowth! No active raids! Report one with **!raid <name> <location>**."))
                return
            else:
                await Meowth.send_message(channel, listmsg)
                return

        if checks.check_raidchannel(ctx):
            if checks.check_raidactive(ctx):
                bulletpoint = parse_emoji(ctx.message.server, ":small_blue_diamond:")
                starttime = False
                try:
                    starttime = server_dict[server.id]['raidchannel_dict'][channel.id]['starttime']
                except KeyError:
                    pass
                rc_d = server_dict[server.id]['raidchannel_dict'][channel.id]
                if rc_d['type'] == 'egg' and rc_d['pokemon'] == '':
                    listmsg += "\n" + bulletpoint + await _interest(ctx)
                    listmsg += "\n" + bulletpoint
                    listmsg += await print_raid_timer(channel)
                    if starttime and starttime > now:
                        listmsg += "\nMeowth! The next group will be starting at {}".format(starttime.strftime("%I:%M %p (%H:%M)"))
                else:
                    listmsg += "\n" + bulletpoint + await _interest(ctx)
                    listmsg += "\n" + bulletpoint + await _otw(ctx)
                    listmsg += "\n" + bulletpoint + await _waiting(ctx)
                    listmsg += "\n" + bulletpoint + await _lobbylist(ctx)
                    listmsg += "\n" + bulletpoint + await print_raid_timer(channel)
                    if starttime and starttime > now:
                        listmsg += "\nThe next group will be starting at **{}**".format(starttime.strftime("%I:%M %p (%H:%M)"))
                await Meowth.send_message(channel, listmsg)
                return

@Meowth.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def omw(ctx):
    await Meowth.send_message(ctx.message.channel, content = _("Meowth! Hey {member}, I don't know if you meant **!coming** to say that you are coming or **!list coming** to see the other trainers on their way").format(member=ctx.message.author.mention))

@list.command(pass_context=True)
@checks.activeraidchannel()
async def interested(ctx):
    """Lists the number and users who are interested in the raid.

    Usage: !list interested
    Works only in raid channels."""
    listmsg = "**Meowth!**"
    listmsg += await _interest(ctx)
    await Meowth.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def coming(ctx):
    """Lists the number and users who are coming to a raid.

    Usage: !list coming
    Works only in raid channels."""
    listmsg = "**Meowth!**"
    listmsg += await _otw(ctx)
    await Meowth.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def here(ctx):
    """List the number and users who are present at a raid.

    Usage: !list here
    Works only in raid channels."""
    listmsg = "**Meowth!**"
    listmsg += await _waiting(ctx)
    await Meowth.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def lobby(ctx):
    """List the number and users who are in the raid lobby.

    Usage: !list lobby
    Works only in raid channels."""
    listmsg = "**Meowth!**"
    listmsg += await _lobbylist(ctx)
    await Meowth.send_message(ctx.message.channel, listmsg)

@list.command(pass_context=True)
@checks.activeraidchannel()
async def teams(ctx):
    """List the teams for the users that have RSVP'd to a raid.

    Usage: !list teams
    Works only in raid channels."""
    listmsg = "**Meowth!**"
    listmsg += await _teamlist(ctx)
    await Meowth.send_message(ctx.message.channel, listmsg)

@Meowth.command(pass_context=True)
@commands.has_permissions(manage_server=True)
@checks.raidchannel()
async def clearstatus(ctx):
    """Clears raid channel status lists.

    Usage: !clearstatus
    Only usable by admins."""
    try:
        server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'] = {}
        await Meowth.send_message(ctx.message.channel,"Meowth! Raid status lists have been cleared!")
    except KeyError:
        pass

@Meowth.command(pass_context=True)
@checks.activeraidchannel()
async def duplicate(ctx):
    """A command to report a raid channel as a duplicate.

    Usage: !duplicate
    Works only in raid channels. When three users report a channel as a duplicate,
    Meowth deactivates the channel and marks it for deletion."""
    channel = ctx.message.channel
    author = ctx.message.author
    server = ctx.message.server
    rc_d = server_dict[server.id]['raidchannel_dict'][channel.id]
    t_dict =rc_d['trainer_dict']
    can_manage = channel.permissions_for(author).manage_channels

    if can_manage:
        dupecount = 2
        rc_d['duplicate'] = dupecount
    else:
        if author.id in t_dict:
            try:
                if t_dict[author.id]['dupereporter']:
                    dupeauthmsg = await Meowth.send_message(channel,_("Meowth! You've already made a duplicate report for this raid!"))
                    await asyncio.sleep(10)
                    await Meowth.delete_message(dupeauthmsg)
                    return
                else:
                    t_dict[author.id]['dupereporter'] = True
            except KeyError:
                t_dict[author.id]['dupereporter'] = True
        else:
            t_dict[author.id] = {
                'status' : '',
                'dupereporter' : True
                }
        try:
            dupecount = rc_d['duplicate']
        except KeyError:
            dupecount = 0
            rc_d['duplicate'] = dupecount

    dupecount += 1
    rc_d['duplicate'] = dupecount

    if dupecount >= 3:
        rusure = await Meowth.send_message(channel,_("Meowth! Are you sure you wish to remove this raid?"))
        await asyncio.sleep(0.25)
        await Meowth.add_reaction(rusure,"✅") #checkmark
        await asyncio.sleep(0.25)
        await Meowth.add_reaction(rusure,"❎") #cross
        def check(react,user):
            if user.id != author.id:
                return False
            return True

        res = await Meowth.wait_for_reaction(['✅','❎'], message=rusure, check=check, timeout=60)

        if res is not None:
            if res.reaction.emoji == "❎":
                await Meowth.delete_message(rusure)
                confirmation = await Meowth.send_message(channel,_("Duplicate Report cancelled."))
                logger.info("Duplicate Report - Cancelled - "+channel.name+" - Report by "+author.name)
                dupecount = 2
                server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate'] = dupecount
                await asyncio.sleep(10)
                await Meowth.delete_message(confirmation)
                return
            elif res.reaction.emoji == "✅":
                await Meowth.delete_message(rusure)
                await Meowth.send_message(channel,"Duplicate Confirmed")
                logger.info("Duplicate Report - Channel Expired - "+channel.name+" - Last Report by "+author.name)
                await expire_channel(channel)
                return
        else:
            await Meowth.delete_message(rusure)
            confirmation = await Meowth.send_message(channel,_("Duplicate Report Timed Out."))
            logger.info("Duplicate Report - Timeout - "+channel.name+" - Report by "+author.name)
            dupecount = 2
            server_dict[server.id]['raidchannel_dict'][channel.id]['duplicate'] = dupecount
            await asyncio.sleep(10)
            await Meowth.delete_message(confirmation)
    else:
        rc_d['duplicate'] = dupecount
        confirmation = await Meowth.send_message(channel,_("Duplicate report #{duplicate_report_count} received.").format(duplicate_report_count=str(dupecount)))
        logger.info("Duplicate Report - "+channel.name+" - Report #"+str(dupecount)+ "- Report by "+author.name)
        return

@Meowth.group(pass_context=True)
@checks.activeraidchannel()
async def location(ctx):
    """Get raid location.

    Usage: !location
    Works only in raid channels. Gives the raid location link."""
    if ctx.invoked_subcommand is None:
        message = ctx.message
        server = message.server
        channel = message.channel
        rc_d = server_dict[server.id]['raidchannel_dict']
        raidmsg = await Meowth.get_message(channel, rc_d[channel.id]['raidmessage'])
        location = rc_d[channel.id]['address']
        report_channel = Meowth.get_channel(rc_d[channel.id]['reportcity'])
        oldembed = raidmsg.embeds[0]
        locurl = oldembed['url']
        newembed = discord.Embed(title=oldembed['title'],url=locurl,colour=server.me.colour)
        newembed.add_field(name=oldembed['fields'][0]['name'],value=oldembed['fields'][0]['value'],inline=True)
        newembed.add_field(name=oldembed['fields'][1]['name'],value=oldembed['fields'][1]['value'],inline=True)
        newembed.set_footer(text=oldembed['footer']['text'], icon_url=oldembed['footer']['icon_url'])
        newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
        locationmsg = await Meowth.send_message(channel, content = _("Meowth! Here's the current location for the raid!\nDetails: {location}").format(location = location), embed = newembed)
        await asyncio.sleep(60)
        await Meowth.delete_message(locationmsg)

@location.command(pass_context=True)
@checks.activeraidchannel()
async def new(ctx):
    """Change raid location.

    Usage: !location new <new address>
    Works only in raid channels. Changes the google map links."""

    message = ctx.message
    location_split = message.content.lower().split()
    del location_split[0]
    del location_split[0]
    if len(location_split) < 1:
        await Meowth.send_message(message.channel, _("Meowth! We're missing the new location details! Usage: **!location new <new address>**"))
        return
    else:
        report_channel = Meowth.get_channel(rc_d[r]['reportcity'])
        report_city = report_channel.name

        details = " ".join(location_split)
        if "/maps" in message.content:
            mapsindex = message.content.find("/maps")
            newlocindex = message.content.rfind("http", 0, mapsindex)
            if newlocindex == -1:
                return
            newlocend = message.content.find(" ", newlocindex)
            if newlocend == -1:
                newloc = message.content[newlocindex:]
            else:
                newloc = message.content[newlocindex:newlocend+1]
        else:
            newloc = create_gmaps_query(details, report_channel)

        oldraidmsg = await Meowth.get_message(message.channel, server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidmessage'])
        oldreportmsg = await Meowth.get_message(report_channel, server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidreport'])
        oldembed = oldraidmsg.embeds[0]
        newembed = discord.Embed(title=oldembed['title'],url=newloc,colour=message.server.me.colour)
        newembed.add_field(name=oldembed['fields'][0]['name'],value=oldembed['fields'][0]['value'],inline=True)
        newembed.add_field(name=oldembed['fields'][1]['name'],value=oldembed['fields'][1]['value'],inline=True)
        newembed.set_footer(text=oldembed['footer']['text'], icon_url=oldembed['footer']['icon_url'])
        newembed.set_thumbnail(url=oldembed['thumbnail']['url'])
        try:
            newraidmsg = await Meowth.edit_message(oldraidmsg, new_content=oldraidmsg.content, embed=newembed)
        except:
            pass
        try:
            newreportmsg = await Meowth.edit_message(oldreportmsg, new_content=oldreportmsg.content, embed=newembed)
        except:
            pass
        server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidmessage'] = newraidmsg.id
        server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['raidreport'] = newreportmsg.id
        otw_list = []
        trainer_dict = copy.deepcopy(server_dict[message.server.id]['raidchannel_dict'][message.channel.id]['trainer_dict'])
        for trainer in trainer_dict.keys():
            if trainer_dict[trainer]['status']=='omw':
                user = message.server.get_member(trainer)
                otw_list.append(user.mention)
        await Meowth.send_message(message.channel, content = _("Meowth! Someone has suggested a different location for the raid! Trainers {trainer_list}: make sure you are headed to the right place!").format(trainer_list=", ".join(otw_list)), embed = newembed)
        return

async def _teamlist(ctx):
    redlist = []
    redmaybe = 0
    redcoming = 0
    redwaiting = 0
    bluelist = []
    bluemaybe = 0
    bluecoming = 0
    bluewaiting = 0
    yellowlist = []
    yellowmaybe = 0
    yellowcoming = 0
    yellowwaiting = 0
    othermaybe = 0
    othercoming = 0
    otherwaiting = 0
    teamliststr = ""
    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status'] =='maybe' or trainer_dict[trainer]['status'] =='omw' or trainer_dict[trainer]['status'] =='waiting':
            user = ctx.message.server.get_member(trainer)
            for role in user.roles:
                if role.name == "mystic":
                    bluelist.append(user.id)
                elif role.name == "valor":
                    redlist.append(user.id)
                elif role.name =="instinct":
                    yellowlist.append(user.id)
    for trainer in redlist:
        if trainer_dict[trainer]['status'] == "waiting":
            redwaiting += 1
            otherwaiting += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "omw":
            redcoming += 1
            othercoming += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "maybe":
            redmaybe += 1
            othermaybe += trainer_dict[trainer]['count']-1
    for trainer in bluelist:
        if trainer_dict[trainer]['status'] == "waiting":
            bluewaiting += 1
            otherwaiting += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "omw":
            bluecoming += 1
            othercoming += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "maybe":
            bluemaybe += 1
            othermaybe += trainer_dict[trainer]['count']-1
    for trainer in yellowlist:
        if trainer_dict[trainer]['status'] == "waiting":
            yellowwaiting += 1
            otherwaiting += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "omw":
            yellowcoming += 1
            othercoming += trainer_dict[trainer]['count']-1
        elif trainer_dict[trainer]['status'] == "maybe":
            yellowmaybe += 1
            othermaybe += trainer_dict[trainer]['count']-1

    if len(redlist) > 0:
        teamliststr += _("{red_emoji} **{red_number} total,** {redmaybe} interested, {redcoming} coming, {redwaiting} waiting {red_emoji}\n").format(red_number=len(redlist), red_emoji=parse_emoji(ctx.message.server, config['team_dict']['valor']), redmaybe=redmaybe, redcoming=redcoming, redwaiting=redwaiting)
    if len(bluelist) > 0:
        teamliststr += _("{blue_emoji} **{blue_number} total,** {bluemaybe} interested, {bluecoming} coming, {bluewaiting} waiting {blue_emoji}\n").format(blue_number=len(bluelist), blue_emoji=parse_emoji(ctx.message.server, config['team_dict']['mystic']), bluemaybe=bluemaybe, bluecoming=bluecoming, bluewaiting=bluewaiting)
    if len(yellowlist) > 0:
        teamliststr += _("{yellow_emoji} **{yellow_number} total,** {yellowmaybe} interested, {yellowcoming} coming, {yellowwaiting} waiting {yellow_emoji}\n").format(yellow_number=len(yellowlist), yellow_emoji=parse_emoji(ctx.message.server, config['team_dict']['instinct']), yellowmaybe=yellowmaybe, yellowcoming=yellowcoming, yellowwaiting=yellowwaiting)
    if (othermaybe+othercoming+otherwaiting) > 0:
        teamliststr += _("{grey_emoji} **{grey_number} unknown,** {greymaybe} interested, {greycoming} coming, {greywaiting} waiting {grey_emoji}\n").format(grey_number=othermaybe+othercoming+otherwaiting, grey_emoji=parse_emoji(ctx.message.server, config['type_id_dict']['normal']), greymaybe=othermaybe, greycoming=othercoming, greywaiting=otherwaiting)


    if (len(redlist)+len(bluelist)+len(yellowlist)) > 0:
        listmsg = _(" Team numbers for the raid:\n{}").format(teamliststr)
    else:
        listmsg = _(" I couldn't find any trainer with a team!")

    return listmsg

async def _interest(ctx):
    ctx_maybecount = 0
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[ctx.message.channel.server.id]['offset'])
    # Grab all trainers who are maybe and sum
    # up their counts
    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])
    for trainer in trainer_dict.values():
        if trainer['status'] == "maybe":
            ctx_maybecount += trainer['count']

    # If at least 1 person is interested,
    # add an extra message indicating who it is.
    maybe_exstr = ""
    maybe_list = []
    name_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='maybe':
            user = ctx.message.server.get_member(trainer)
            name_list.append("**"+user.name+"**")
            maybe_list.append(user.mention)
    if ctx_maybecount > 0:
        if now.time() >= datetime.time(5,0) and now.time() <= datetime.time(21,0):
            maybe_exstr = _(" including {trainer_list} and the people with them! Let them know if there is a group forming").format(trainer_list=", ".join(maybe_list))
        else:
            maybe_exstr = _(" including {trainer_list} and the people with them! Let them know if there is a group forming").format(trainer_list=", ".join(name_list))
    listmsg = (_(" {trainer_count} interested{including_string}!").format(trainer_count=str(ctx_maybecount), including_string=maybe_exstr))

    return listmsg

async def _otw(ctx):

    ctx_omwcount = 0
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[ctx.message.channel.server.id]['offset'])
    # Grab all trainers who are :omw: and sum
    # up their counts
    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])
    for trainer in trainer_dict.values():
        if trainer['status'] == "omw":
            ctx_omwcount += trainer['count']

    # If at least 1 person is on the way,
    # add an extra message indicating who it is.
    otw_exstr = ""
    otw_list = []
    name_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='omw':
            user = ctx.message.server.get_member(trainer)
            name_list.append("**"+user.name+"**")
            otw_list.append(user.mention)
    if ctx_omwcount > 0:
        if now.time() >= datetime.time(5,0) and now.time() <= datetime.time(21,0):
            otw_exstr = _(" including {trainer_list} and the people with them! Be considerate and wait for them if possible").format(trainer_list=", ".join(otw_list))
        else:
            otw_exstr = _(" including {trainer_list} and the people with them! Be considerate and wait for them if possible").format(trainer_list=", ".join(name_list))
    listmsg = (_(" {trainer_count} on the way{including_string}!").format(trainer_count=str(ctx_omwcount), including_string=otw_exstr))
    return listmsg

async def _waiting(ctx):

    ctx_waitingcount = 0
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[ctx.message.channel.server.id]['offset'])
    # Grab all trainers who are :here: and sum
    # up their counts
    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])
    for trainer in trainer_dict.values():
        if trainer['status'] == "waiting":
            ctx_waitingcount += trainer['count']

    # If at least 1 person is waiting,
    # add an extra message indicating who it is.
    waiting_exstr = ""
    waiting_list = []
    name_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='waiting':
            user = ctx.message.server.get_member(trainer)
            name_list.append("**"+user.name+"**")
            waiting_list.append(user.mention)
    if ctx_waitingcount > 0:
        if now.time() >= datetime.time(5,0) and now.time() <= datetime.time(21,0):
            waiting_exstr = _(" including {trainer_list} and the people with them! Be considerate and let them know if and when you'll be there").format(trainer_list=", ".join(waiting_list))
        else:
            waiting_exstr = _(" including {trainer_list} and the people with them! Be considerate and let them know if and when you'll be there").format(trainer_list=", ".join(name_list))
    listmsg = (_(" {trainer_count} waiting at the raid{including_string}!").format(trainer_count=str(ctx_waitingcount), including_string=waiting_exstr))
    return listmsg

async def _lobbylist(ctx):

    ctx_lobbycount = 0
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=server_dict[ctx.message.channel.server.id]['offset'])
    # Grab all trainers who are :omw: and sum
    # up their counts
    trainer_dict = copy.deepcopy(server_dict[ctx.message.server.id]['raidchannel_dict'][ctx.message.channel.id]['trainer_dict'])
    for trainer in trainer_dict.values():
        if trainer['status'] == "lobby":
            ctx_lobbycount += trainer['count']

    # If at least 1 person is on the way,
    # add an extra message indicating who it is.
    lobby_exstr = ""
    lobby_list = []
    name_list = []
    for trainer in trainer_dict.keys():
        if trainer_dict[trainer]['status']=='lobby':
            user = ctx.message.server.get_member(trainer)
            name_list.append("**"+user.name+"**")
            lobby_list.append(user.mention)
    if ctx_lobbycount > 0:
        if now.time() >= datetime.time(5,0) and now.time() <= datetime.time(21,0):
            lobby_exstr = _(" including {trainer_list} and the people with them! Use **!lobby** if you are joining them or **!backout** to request a backout").format(trainer_list=", ".join(lobby_list))
        else:
            lobby_exstr = _(" including {trainer_list} and the people with them! Use **!lobby** if you are joining them or **!backout** to request a backout").format(trainer_list=", ".join(name_list))
    listmsg = (_(" {trainer_count} in the lobby{including_string}!").format(trainer_count=str(ctx_lobbycount), including_string=lobby_exstr))
    return listmsg

@Meowth.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def interest(ctx):
    await Meowth.send_message(ctx.message.channel, _("Meowth! We've moved this command to **!list interested**."))

@Meowth.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def otw(ctx):
    await Meowth.send_message(ctx.message.channel, _("Meowth! We've moved this command to **!list coming**."))

@Meowth.command(pass_context=True, hidden=True)
@checks.activeraidchannel()
async def waiting(ctx):
    await Meowth.send_message(ctx.message.channel, _("Meowth! We've moved this command to **!list here**."))

@Meowth.command(pass_context=True)
@checks.citychannel()
async def invite(ctx):
    """Join an EX Raid by showing your invite.

    Usage: !invite [image attachment]
    If the image isn't added at the same time as the command, Meowth will wait 30 seconds for a followup message containing the image."""
    if ctx.message.attachments:
        await _invite(ctx)
    else:
        wait_msg = await Meowth.send_message(ctx.message.channel,_("Meowth! I'll wait for you to send your pass!"))
        def check(msg):
            if msg.channel == ctx.message.channel and ctx.message.author.id == msg.author.id:
                if msg.attachments:
                    return True
        invitemsg = await Meowth.wait_for_message(author = ctx.message.author, check=check, timeout=30)
        if invitemsg is not None:
            ctx.message = invitemsg
            await _invite(ctx)
            return
        else:
            await Meowth.delete_message(wait_msg)
            await Meowth.send_message(ctx.message.channel, "Meowth! You took too long to show me a screenshot of your invite! Retry when you're ready.")
            return

async def _invite(ctx):
    if 'https://cdn.discordapp.com' in ctx.message.attachments[0]['url']:
        if 'png' in ctx.message.attachments[0]['url'].lower() or 'jpg' in ctx.message.attachments[0]['url'].lower():
            fd = requests.get(ctx.message.attachments[0]['url'])
            img = Image.open(BytesIO(fd.content))
            width, height = img.size
            new_height = 3500
            new_width  = int(new_height * width / height)
            img = img.resize((new_width, new_height), Image.BICUBIC)
            img = img.filter(ImageFilter.EDGE_ENHANCE)
            enh = ImageEnhance.Brightness(img)
            img = enh.enhance(0.4)
            enh = ImageEnhance.Contrast(img)
            img = enh.enhance(4)
            txt = pytesseract.image_to_string(img, config=tesseract_config)
            if 'EX Raid Battle' in txt or "This is a reward" in txt or "Please visit the Gym" in txt:
                exraidlist = ''
                exraid_dict = {}
                exraidcount = 0
                for channelid in server_dict[ctx.message.server.id]['raidchannel_dict']:
                    if not discord.utils.get(ctx.message.server.channels, id = channelid):
                        continue
                    if server_dict[ctx.message.server.id]['raidchannel_dict'][channelid]['egglevel'] == 'EX' or server_dict[ctx.message.server.id]['raidchannel_dict'][channelid]['type'] == 'exraid':
                        channel = Meowth.get_channel(channelid)
                        if channel.mention != '#deleted-channel':
                            exraidcount += 1
                            exraidlist += '\n' + str(exraidcount) + '.   ' + channel.mention
                            exraid_dict[str(exraidcount)] = channel
                if exraidcount > 0:
                    await Meowth.send_message(ctx.message.channel, "Meowth! {0}, it looks like you've got an EX Raid invitation! The following {1} EX Raids have been reported: \n {2} \n Reply with the number of the EX Raid you have been invited to. If none of them match your invite, type 'N' and report it with **!exraid**".format(ctx.message.author.mention, str(exraidcount), exraidlist))
                    reply = await Meowth.wait_for_message(author=ctx.message.author)
                    if reply.content.lower() == 'n':
                        await Meowth.send_message(ctx.message.channel, "Meowth! Be sure to report your EX Raid with **!exraid**!")
                    elif not reply.content.isdigit() or int(reply.content) > exraidcount:
                        await Meowth.send_message(ctx.message.channel, "Meowth! I couldn't tell which EX Raid you meant! Try the **!invite** command again, and make sure you respond with the number of the channel that matches!")
                    elif int(reply.content) <= exraidcount and int(reply.content) > 0:
                        overwrite = discord.PermissionOverwrite()
                        overwrite.send_messages = True
                        overwrite.read_messages = True
                        exraid_channel = exraid_dict[str(int(reply.content))]
                        await Meowth.edit_channel_permissions(exraid_channel, ctx.message.author, overwrite)
                        await Meowth.send_message(ctx.message.channel, "Meowth! Alright {0}, you can now send messages in {1}! Make sure you let the trainers in there know if you can make it to the EX Raid!".format(ctx.message.author.mention, exraid_channel.mention))
                    else:
                        await Meowth.send_message(ctx.message.channel, "Meowth! I couldn't understand your reply! Try the **!invite** command again!")
                else:
                    await Meowth.send_message(ctx.message.channel, "Meowth! No EX Raids have been reported in this server! Use **!exraid** to report one!")
            else:
                await Meowth.send_message(ctx.message.channel, "Meowth! That doesn't look like an EX Raid invitation to me! If it is, please message an admin to get added to the EX Raid channel manually!")
        else:
            await Meowth.send_message(ctx.message.channel, "Meowth! Your attachment was not a supported image format!")
    else:
        await Meowth.send_message(ctx.message.channel, "Meowth! Please upload your screenshot directly to Discord!")

@Meowth.command(pass_context=True)
@commands.has_permissions(manage_server=True)
async def recover(ctx):
    if checks.check_wantchannel(ctx) or checks.check_citychannel(ctx) or checks.check_raidchannel(ctx) or checks.check_eggchannel(ctx) or checks.check_exraidchannel(ctx):
        await Meowth.send_message(ctx.message.channel, "Meowth! I can't recover this channel because I know about it already!")
    else:
        channel = ctx.message.channel
        server = channel.server
        name = channel.name
        topic = channel.topic
        egg = re.match('level-[1-5]-egg', name)
        if egg:
            raidtype = 'egg'
            chsplit = egg.string.split('-')
            del chsplit[0]
            egglevel = chsplit[0]
            del chsplit[0]
            del chsplit[0]
            raid_details = " ".join(chsplit)
            raid_details = raid_details.strip()
            if not topic:
                exp = time.time() + 60 * raid_info['raid_eggs'][egglevel]['hatchtime']
                manual_timer = False
            else:
                topicsplit = topic.split('|')
                localhatch = datetime.datetime.strptime(topicsplit[0][:-9], "Hatches on %B %d at %I:%M %p")
                utchatch = localhatch - datetime.timedelta(hours=server_dict[server.id]['offset'])
                exp = utchatch.replace(tzinfo=datetime.timezone.utc).timestamp()
                manual_timer = True
            pokemon = ''
            if len(raid_info['raid_eggs'][egglevel]['pokemon']) == 1:
                pokemon = raid_info['raid_eggs'][egglevel]['pokemon'][0]
        elif name.split('-')[0] in get_raidlist():
            raidtype = 'raid'
            chsplit = name.split('-')
            pokemon = chsplit[0]
            del chsplit[0]
            raid_details = " ".join(chsplit)
            raid_details = raid_details.strip()
            if not topic:
                exp = time.time() + 60 * 45
                manual_timer = False
            else:
                localend = datetime.datetime.strptime(topic[:-8], "Ends on %B %d at %I:%M %p")
                utcend = localend - datetime.timedelta(hours=server_dict[server.id]['offset'])
                exp = utcend.replace(tzinfo=datetime.timezone.utc).timestamp()
                manual_timer = True
        elif name.split('-')[0] == 'ex':
            raidtype = 'egg'
            egglevel = 'EX'
            chsplit = name.split('-')
            del chsplit[0]
            del chsplit[0]
            del chsplit[0]
            raid_details = " ".join(chsplit)
            raid_details = raid_details.strip()
            if not topic:
                exp = time.time() + 60*60*24*14
                manual_timer = False
            else:
                topicsplit = topic.split('|')
                localhatch = datetime.datetime.strptime(topicsplit[0][:-9], "Hatches on %B %d at %I:%M %p")
                utchatch = localhatch - datetime.timedelta(hours=server_dict[server.id]['offset'])
                exp = utchatch.replace(tzinfo=datetime.timezone.utc).timestamp()
                manual_timer = True
            pokemon = ''
            if len(raid_info['raid_eggs']['EX']['pokemon']) == 1:
                pokemon = raid_info['raid_eggs']['EX']['pokemon'][0]
        else:
            await Meowth.send_message(channel, "Meowth! I couldn't recognize this as a raid channel!")
            return
        server_dict[channel.server.id]['raidchannel_dict'][channel.id] = {
            'reportcity' : None,
            'trainer_dict' : {},
            'exp': exp,
            'manual_timer': manual_timer,
            'active': True,
            'raidmessage': None,
            'raidreport': None,
            'address': raid_details,
            'type': raidtype,
            'pokemon' : pokemon,
            'egglevel': egglevel
            }
        recovermsg = "Meowth! This channel has been recovered! However, I can't remember if anyone RSVPed to this raid."
        if not manual_timer:
            if raidtype == "egg":
                action = "hatch"
            elif raidtype == "raid":
                action = "end"
            recovermsg += "I'm also not sure when this {raidtype} will {action}, so please use **!timerset** if you can!".format(raidtype, action)
        await Meowth.send_message(channel, recovermsg)

@Meowth.command(pass_context=True)
@checks.activeraidchannel()
async def backout(ctx):
    message = ctx.message
    channel = message.channel
    author = message.author
    server = channel.server
    trainer_dict = server_dict[server.id]['raidchannel_dict'][channel.id]['trainer_dict']
    if author.id in trainer_dict and trainer_dict[author.id]['status'] == "lobby":
        trainer_dict[author.id]['status'] = "waiting"
        lobby_list = []
        for trainer in trainer_dict:
            if trainer_dict[trainer]['status'] == "lobby":
                user = server.get_member(trainer)
                lobby_list.append(user.mention)
                trainer_dict[trainer]['status'] = "waiting"
        if not lobby_list:
            await Meowth.send_message(channel, "Meowth! There's no one else in the lobby for this raid!")
            try:
                del server_dict[server.id]['raidchannel_dict'][channel.id]['lobby']
            except KeyError:
                pass
            return
        await Meowth.send_message(channel, "Meowth! {author} has indicated that the group consisting of {lobby_list} and the people with them has backed out of the lobby! If this is inaccurate, please use **!lobby** or **!cancel** to help me keep my lists accurate!".format(author=author.mention, lobby_list=", ".join(lobby_list)))
        try:
            del server_dict[server.id]['raidchannel_dict'][channel.id]['lobby']
        except KeyError:
            pass
    else:
        lobby_list = []
        trainer_list = []
        for trainer in trainer_dict:
            if trainer_dict[trainer]['status'] == "lobby":
                user = server.get_member(trainer)
                lobby_list.append(user.mention)
                trainer_list.append(trainer)
        if not lobby_list:
            await Meowth.send_message(channel, "Meowth! There's no one in the lobby for this raid!")
            return
        backoutmsg = await Meowth.send_message(channel, "Meowth! {author} has requested a backout! If one of the following trainers reacts with the check mark, I will assume the group is backing out of the raid lobby as requested! {lobby_list}".format(author=author.mention, lobby_list = ", ".join(lobby_list)))
        await asyncio.sleep(0.25)
        await Meowth.add_reaction(backoutmsg,"✅")
        def check(react,user):
            if user.mention not in lobby_list:
                return False
            return True
        res = await Meowth.wait_for_reaction(emoji="✅", timeout=30, message=backoutmsg, check=check)
        if res:
            for trainer in trainer_list:
                if trainer in trainer_dict:
                    trainer_dict[trainer]['status'] = "waiting"
            await Meowth.send_message(channel, "Meowth! {user} confirmed the group is backing out!".format(user=res.user.mention))
            try:
                del server_dict[server.id]['raidchannel_dict'][channel.id]['lobby']
            except KeyError:
                pass

try:
    event_loop.run_until_complete(Meowth.start(config['bot_token']))
except discord.LoginFailure:
    logger.critical("Invalid token")
    event_loop.run_until_complete(Meowth.logout())
    Meowth._shutdown_mode = 0
except KeyboardInterrupt:
    logger.info("Keyboard interrupt detected. Quitting...")
    event_loop.run_until_complete(Meowth.logout())
    Meowth._shutdown_mode = 0
except Exception as e:
    logger.critical("Fatal exception", exc_info=e)
    event_loop.run_until_complete(Meowth.logout())
finally:
    pass

sys.exit(Meowth._shutdown_mode)

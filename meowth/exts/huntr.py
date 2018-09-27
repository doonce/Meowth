import asyncio
import copy
import re
import time
import datetime
import dateparser
import urllib

import discord
from discord.ext import commands

import meowth
from meowth import utils, checks

class Huntr:
    def __init__(self, bot):
        self.bot = bot
        test = meowth.test(1)

    """Handlers"""

    async def on_message(self, message):
        ctx = await self.bot.get_context(message)
        if not ctx.guild:
            return
        if message.guild and message.webhook_id and ("!raid" in message.content or "!raidegg" in message.content or "!wild" in message.content):
            await on_pokealarm(ctx)
        if (str(message.author) == 'GymHuntrBot#7279') or (str(message.author) == 'HuntrBot#1845'):
            await on_huntr(ctx)

    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        try:
            message = await channel.get_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        guild = message.guild
        try:
            user = guild.get_member(payload.user_id)
        except AttributeError:
            return
        pokealarm_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokealarm_dict',{}))
        pokehuntr_dict = copy.deepcopy(ctx.bot.guild_dict[channel.guild.id].get('pokehuntr_dict',{}))
        if message.id in pokealarm_dict.keys() and not user.bot and str(payload.emoji) == "✅":
            await on_pokealarm(ctx, user)
        if message.id in pokehuntr_dict.keys() and not user.bot and str(payload.emoji) == "✅":
            await on_huntr(ctx, user)

    async def on_huntr(self, ctx, reactuser=None):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime('%I:%M %p')
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
        pokehuntr_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokehuntr_dict',{}))
        if not reactuser:
            if message.embeds and (message.author.id == 329412230481444886 or message.author.id == 295116861920772098 or message.author.id == message.guild.me.id):
                try:
                    huntrgps = message.embeds[0].url.split('#')[1]
                except IndexError:
                    req = urllib.request.Request(message.embeds[0].url, headers={
                        'User-Agent': 'Magic Browser',
                    })
                    con = urllib.request.urlopen(req)
                    try:
                        huntrgps = con.geturl().split('#')[1]
                        con.close()
                    except IndexError:
                        source = str(con.read().decode('utf8').replace('\n', '').replace(' ', ''))
                        sourceindex = source.find('huntr.com/#')
                        newsourceindex = source.rfind('http', 0, sourceindex)
                        newsourceend = source.find('"', newsourceindex)
                        newsource = source[newsourceindex:newsourceend]
                        huntrgps = newsource.split('#')[1]
                        con.close()
            if (message.author.id == 329412230481444886 or message.author.id == message.guild.me.id) and message.embeds:
                if (len(message.embeds[0].title.split(' ')) == 5) and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autoraid']:
                    ghduplicate = False
                    ghraidlevel = message.embeds[0].title.split(' ')[1]
                    ghdesc = message.embeds[0].description.splitlines()
                    ghgym = ghdesc[0][2:(- 3)]
                    ghpokeid = ghdesc[1]
                    ghmoves = '\u200b'
                    if len(ghdesc[2].split()) > 3:
                        ghmoves = ghdesc[2].split('**Moves:** ')[1]
                    ghtime = ghdesc[3].split(' ')
                    ghhour = ghtime[2]
                    ghminute = int(ghtime[4].zfill(2))
                    ghsec = int(ghtime[6].zfill(2))
                    huntr = '!raid {0} {1} {2}|{3}|{4}'.format(ghpokeid, ghgym, ghminute, huntrgps, ghmoves)
                    ghtimestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(ghminute), seconds=int(ghsec))).strftime('%I:%M %p')
                    await message.delete()
                    for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                        try:
                            if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['gymhuntrgps'] == huntrgps:
                                ghduplicate = True
                                channel = self.bot.get_channel(channelid)
                                if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['type'] == 'egg':
                                    await _eggtoraid(ghpokeid.lower().strip(), channel, author=message.author, huntr=huntr)
                                raidmsg = await channel.get_message(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['raidmessage'])
                                if raidmsg.embeds[0].fields[2].name != ghmoves:
                                    await channel.send(_("This {pokemon}'s moves are: **{moves}**").format(pokemon=ghpokeid, moves=ghmoves))
                        except KeyError:
                            pass
                    if (ghduplicate == False) and (int(ghraidlevel) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['raidlvls']):
                        await self._raid(ctx, content="",huntr=huntr)
                    elif (ghduplicate is False) and (int(ghraidlevel) not in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['raidlvls']):
                        raid = discord.utils.get(message.guild.roles, name=ghpokeid.lower().strip())
                        if raid is None:
                            roletest = ""
                        else:
                            roletest = _("{pokemon} - ").format(pokemon=raid.mention)
                        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the raid!'), url=_('https://www.google.com/maps/dir/Current+Location/{0}').format(huntrgps), colour=message.guild.me.colour)
                        raid_number = ctx.bot.pkmn_info['pokemon_list'].index(ghpokeid.lower().strip()) + 1
                        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/{0}_.png?cache=0'.format(str(raid_number).zfill(3))
                        raid_embed.add_field(name='**Details:**', value=_('{pokemon} ({pokemonnumber}) {type}\n{moves}').format(pokemon=ghpokeid.title(), pokemonnumber=str(raid_number), type=''.join(utils.get_type(ctx.bot, message.guild, raid_number)), moves=ghmoves), inline=True)
                        raid_embed.add_field(name='**Weaknesses:**', value=_('{weakness_list}').format(weakness_list=weakness_to_str(message.guild, get_weaknesses(ghpokeid.lower().strip()))), inline=True)
                        raid_embed.add_field(name='**Location:**', value=_('{raid_details}').format(raid_details='\n'.join(textwrap.wrap(ghgym, width=30))), inline=True)
                        raid_embed.add_field(name='**Expires in:**', value=_('{minutes} mins ({ghtimestamp})').format(minutes=ghminute, ghtimestamp=ghtimestamp), inline=True)
                        raid_embed.set_thumbnail(url=raid_img_url)
                        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=_('https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}'.format(user=message.author, format='jpg', size=32)))
                        raidreport = await message.channel.send(content=_('{roletest}Meowth! {pokemon} raid reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(roletest=roletest,pokemon=ghpokeid.title(), member=message.author.mention, location_details=ghgym), embed=raid_embed)
                        timeout = (int(ghminute) * 60)
                        expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=ghpokeid)
                        await asyncio.sleep(0.25)
                        await raidreport.add_reaction('✅')
                        pokehuntr_dict[raidreport.id] = {
                            "exp":time.time() + timeout,
                            'expedit': {"content":raidreport.content.split(" React")[0],"embedcontent":expiremsg},
                            "reporttype":"raid",
                            "reportchannel":message.channel.id,
                            "level":0,
                            "pokemon":ghpokeid,
                            "reporttime":now,
                            "huntr":huntr,
                            "embed":raid_embed
                        }
                        self.bot.guild_dict[message.guild.id]['pokehuntr_dict'] = pokehuntr_dict
                        return
                elif (len(message.embeds[0].title.split(' ')) == 6) and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autoegg']:
                    ghduplicate = False
                    ghegglevel = message.embeds[0].title.split(' ')[1]
                    ghdesc = message.embeds[0].description.splitlines()
                    ghgym = ghdesc[0][2:(- 3)]
                    ghtime = ghdesc[1].split(' ')
                    ghhour = ghtime[2]
                    ghminute = int(ghtime[4].zfill(2))
                    ghsec = int(ghtime[4].zfill(2))
                    huntr = '!raidegg {0} {1} {2}|{3}'.format(ghegglevel, ghgym, ghminute, huntrgps)
                    ghtimestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(ghminute), seconds=int(ghsec))).strftime('%I:%M %p')
                    await message.delete()
                    for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                        try:
                            if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid]['gymhuntrgps'] == huntrgps:
                                ghduplicate = True
                                break
                        except KeyError:
                            pass
                    if (ghduplicate == False) and (int(ghegglevel) in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['egglvls']):
                        await _raidegg(message, content="",huntr=huntr)
                    elif (ghduplicate is False) and (int(ghegglevel) not in self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['egglvls']):
                        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming raid!'), url=_('https://www.google.com/maps/dir/Current+Location/{0}').format(huntrgps), colour=message.guild.me.colour)
                        raid_embed.add_field(name='**Location:**', value=_('{raid_details}').format(raid_details='\n'.join(textwrap.wrap(ghgym, width=30))), inline=True)
                        raid_embed.add_field(name='**Starting in:**', value=_('{minutes} mins ({ghtimestamp})').format(minutes=ghminute, ghtimestamp=ghtimestamp), inline=True)
                        raid_embed.set_thumbnail(url=_('https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{}.png?cache=0'.format(str(ghegglevel))))
                        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=_('https://cdn.discordapp.com/avatars/{user.id}/{user.avatar}.{format}?size={size}'.format(user=message.author, format='jpg', size=32)))
                        raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. React if you want to make a channel for this raid!').format(level=ghegglevel, member=message.author.mention, location_details=ghgym), embed=raid_embed)
                        timeout = (int(ghminute) * 60)
                        await asyncio.sleep(0.25)
                        await raidreport.add_reaction('✅')
                        pokehuntr_dict[raidreport.id] = {
                            "exp":time.time() + timeout,
                            'expedit': {"content":raidreport.content.split(" React")[0],"embedcontent":expiremsg},
                            "reporttype":"egg",
                            "reportchannel":message.channel.id,
                            "level":ghegglevel,
                            "pokemon":None,
                            "reporttime":now,
                            "huntr":huntr,
                            "embed":raid_embed
                        }
                        self.bot.guild_dict[message.guild.id]['pokehuntr_dict'] = pokehuntr_dict
                        return
            if (message.author.id == 295116861920772098) and message.embeds and self.bot.guild_dict[message.guild.id]['configure_dict']['scanners']['autowild']:
                hpokeid = message.embeds[0].title.split(' ')[2]
                hdesc = message.embeds[0].description.splitlines()
                hexpire = None
                hweather = None
                hiv = None
                huntrgps = "https://pokehuntr.com/#{huntrgps}".format(huntrgps=huntrgps)
                for line in hdesc:
                    if "remaining:" in line.lower():
                        hexpire = line.split(': ')[1][:(- 1)]
                    if "weather:" in line.lower():
                        hweather = line.split(': ')[1][1:(- 1)]
                    if "iv:" in line.lower():
                        hiv = line.split(': ')[1][2:(-2)]
                hextra = "Weather: {hweather}".format(hweather=hweather)
                if hiv:
                    hextra += " / IV: {hiv}".format(hiv=hiv)
                huntr = '!wild {0} {1}|{2}|{3}'.format(hpokeid, huntrgps, hexpire, hextra)
                await message.delete()
                await self._wild(ctx, content="",huntr=huntr)
                return
        else:
            huntr = pokehuntr_dict[message.id]['huntr']
            reporttime = pokehuntr_dict[message.id]['reporttime']
            reporttype = pokehuntr_dict[message.id]['reporttype']
            huntrtime = huntr.split("|")[0][-1]
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            time = int(huntrtime) - int(timediff.minutes)
            huntr = huntr.replace(huntrtime,time)
            if reporttype == "egg":
                raid_channel = await _raidegg(message, content="",huntr=huntr)
            elif reporttype == "raid":
                raid_channel = await _raid(message, content="",huntr=huntr)
            await message.delete()
        return

    async def on_pokealarm(self, message, reactuser=None):
        """Requires a specific message.content format, which is "content" in PokeAlarm
        Raid format = !raid <mon_name> <gym_name> <raid_time_left>|<lat>,<lng>|<quick_move> / <charge_move>
        Raidegg format = !raidegg <egg_lvl> <gym_name> <hatch_time_left>|<lat>,<lng>
        Wild format = !wild <mon_name> <lat>,<lng>|<time_left>|Weather: <weather> / IV: <iv>
        I also recommend to set the username to just PokeAlarm"""
        pokealarm_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id].get('pokealarm_dict',{}))
        if not reactuser:
            reporttype = None
            report = None
            embed = message.embeds[0] if message.embeds else None
            await message.delete()
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            painfo = message.content.split("|")
            if "!raidegg" in message.content.lower():
                reporttype = "egg"
                gps = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:-1]
                level = painfo.pop(0)
                pokeid = None
                time = painfo.pop(-1)[:-1]
                gym = " ".join(painfo)
                timeout = int(time)*60
                expiremsg = _('**This level {level} raid egg has hatched!**').format(level=pokealarm_dict[alertid]['level'])
                huntr = "!raidegg {level} {gym} {time}|{gps}".format(level=level,gym=gym,time=time,gps=gps)
            elif "!raid" in message.content.lower():
                reporttype = "raid"
                gps = painfo.pop(1)
                moves = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:-1]
                pokeid = painfo.pop(0)
                level = 0
                time = painfo.pop(-1)[:-1]
                gym = " ".join(painfo)
                timeout = int(time)*60
                expiremsg = _('**This {pokemon} raid has expired!**').format(pokemon=pokeid.title())
                huntr = "!raid {pokeid} {gym} {time}|{gps}|{moves}".format(pokeid=pokeid,gym=gym,time=time,gps=gps,moves=moves)
            elif "!wild" in message.content.lower():
                reporttype = "wild"
                time = painfo.pop(1).split()
                minutes = time.pop(0)[:-1]
                seconds = time.pop(0)[:-1]
                time = "{min} min {sec} sec".format(min=minutes,sec=seconds)
                weather = painfo.pop(1)
                painfo = " ".join(painfo).split()[1:]
                pokeid = painfo.pop(0)
                location = " ".join(painfo)
                location = "https://www.google.com/maps/dir/Current+Location/{location}".format(location=location)
                despawn = (int(minutes) * 60) + int(seconds)
                huntr = '!wild {pokeid} {gps}|{time}|{weather}'.format(pokeid=pokeid,gps=location,time=time,weather=weather)
            if reporttype == "wild":
                await _wild(message, content="",huntr=huntr)
                return
            else:
                for channelid in self.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                    if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('gymhuntrgps',None) == gps:
                        channel = self.bot.get_channel(channelid)
                        if self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channelid].get('type',None) == 'egg':
                            await _eggtoraid(pokeid.lower().strip(), channel, message.author, message.content)
                        if embed and channel:
                            await channel.send(embed=embed)
                        return
                if self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('alarmaction',None) == 'auto':
                    if reporttype == "egg":
                        huntr = "!raidegg {level} {gym} {time}|{gps}".format(level=level,gym=gym,time=time,gps=gps)
                        raid_channel = await _raidegg(message, content="",huntr=huntr)
                    elif reporttype == "raid":
                        huntr = "!raid {pokeid} {gym} {time}|{gps}|{moves}".format(pokeid=pokeid,gym=gym,time=time,gps=gps,moves=moves)
                        raid_channel = await _raid(message, content="",huntr=huntr)
                    if embed and raid_channel:
                        await raid_channel.send(embed=embed)
                elif self.bot.guild_dict[message.guild.id]['configure_dict']['scanners'].get('alarmaction',None) == 'react':
                    if reporttype == "egg":
                        pamsg = await message.channel.send(("If you want me to report this level {level} egg, just react!").format(level=level),embed=embed)
                    elif reporttype == "raid":
                        pamsg = await message.channel.send(("If you want me to report this {pokeid} raid, just react!").format(pokeid=pokeid),embed=embed)
                    await asyncio.sleep(0.25)
                    await pamsg.add_reaction('✅')
                    pokealarm_dict[pamsg.id] = {
                        "exp":time.time() + timeout,
                        'expedit': {"content":None,"embedcontent":expiremsg},
                        "reporttype":reporttype,
                        "reportchannel":message.channel.id,
                        "level":level,
                        "pokemon":pokeid,
                        "reporttime":now,
                        "huntr":huntr,
                        "embed":embed
                    }
                    self.bot.guild_dict[message.guild.id]['pokealarm_dict'] = pokealarm_dict
        else:
            huntr = pokealarm_dict[message.id]['huntr']
            embed = pokealarm_dict[message.id]['embed']
            reporttime = pokealarm_dict[message.id]['reporttime']
            reporttype = pokealarm_dict[message.id]['reporttype']
            huntrtime = huntr.split("|")[0][-1]
            reacttime = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            timediff = relativedelta(reacttime, reporttime)
            time = int(huntrtime) - int(timediff.minutes)
            huntr = huntr.replace(huntrtime,time)
            if reporttype == "egg":
                raid_channel = await _raidegg(message, content="",huntr=huntr)
            elif reporttype == "raid":
                raid_channel = await _raid(message, content="",huntr=huntr)
            if embed and raid_channel:
                await raid_channel.send(embed=embed)
            await message.delete()

    """Expiry"""

    async def expiry_check(channel):
        logger.info('Expiry_Check - ' + channel.name)
        guild = channel.guild
        global active_raids
        channel = Meowth.get_channel(channel.id)
        if channel not in active_raids:
            active_raids.append(channel)
            logger.info(
                'Expire_Channel - Channel Added To Watchlist - ' + channel.name)
            await asyncio.sleep(0.5)
            while True:
                try:
                    if guild_dict[guild.id]['raidchannel_dict'][channel.id]['active']:
                        if guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp']:
                            if guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp'] <= time.time():
                                if guild_dict[guild.id]['raidchannel_dict'][channel.id]['type'] == 'egg':
                                    pokemon = guild_dict[guild.id]['raidchannel_dict'][channel.id]['pokemon']
                                    egglevel = guild_dict[guild.id]['raidchannel_dict'][channel.id]['egglevel']
                                    if not pokemon and len(raid_info['raid_eggs'][egglevel]['pokemon']) == 1:
                                        pokemon = utils.get_name(Meowth, raid_info['raid_eggs'][egglevel]['pokemon'][0])
                                    elif not pokemon and egglevel == "5" and guild_dict[channel.guild.id]['configure_dict']['settings'].get('regional',None) in raid_info['raid_eggs']["5"]['pokemon']:
                                        pokemon = utils.get_name(Meowth, guild_dict[channel.guild.id]['configure_dict']['settings']['regional'])
                                    if pokemon:
                                        logger.info(
                                            'Expire_Channel - Egg Auto Hatched - ' + channel.name)
                                        try:
                                            active_raids.remove(channel)
                                        except ValueError:
                                            logger.info(
                                                'Expire_Channel - Channel Removal From Active Raid Failed - Not in List - ' + channel.name)
                                        await _eggtoraid(pokemon.lower(), channel, author=None)
                                        break
                                event_loop.create_task(self.expire_channel(channel))
                                try:
                                    active_raids.remove(channel)
                                except ValueError:
                                    logger.info(
                                        'Expire_Channel - Channel Removal From Active Raid Failed - Not in List - ' + channel.name)
                                logger.info(
                                    'Expire_Channel - Channel Expired And Removed From Watchlist - ' + channel.name)
                                break
                except:
                    pass
                await asyncio.sleep(30)
                continue

    async def expire_channel(channel):
        guild = channel.guild
        alreadyexpired = False
        logger.info('Expire_Channel - ' + channel.name)
        # If the channel exists, get ready to delete it.
        # Otherwise, just clean up the dict since someone
        # else deleted the actual channel at some point.
        channel_exists = Meowth.get_channel(channel.id)
        channel = channel_exists
        if (channel_exists == None) and (not Meowth.is_closed()):
            try:
                del guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]
            except KeyError:
                pass
            return
        elif (channel_exists):
            dupechannel = False
            gymhuntrdupe = False
            if guild_dict[guild.id]['raidchannel_dict'][channel.id]['active'] == False:
                alreadyexpired = True
            else:
                guild_dict[guild.id]['raidchannel_dict'][channel.id]['active'] = False
            logger.info('Expire_Channel - Channel Expired - ' + channel.name)
            dupecount = guild_dict[guild.id]['raidchannel_dict'][channel.id].get('duplicate',0)
            if dupecount >= 3:
                if guild_dict[guild.id]['raidchannel_dict'][channel.id]['gymhuntrgps'] is not False:
                    gymhuntrexp = guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp']
                    gymhuntrdupe = True
                dupechannel = True
                guild_dict[guild.id]['raidchannel_dict'][channel.id]['duplicate'] = 0
                guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp'] = time.time()
                if (not alreadyexpired):
                    await channel.send(_('This channel has been successfully reported as a duplicate and will be deleted in 1 minute. Check the channel list for the other raid channel to coordinate in!\nIf this was in error, reset the raid with **!timerset**'))
                delete_time = (guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp'] + (1 * 60)) - time.time()
            elif guild_dict[guild.id]['raidchannel_dict'][channel.id]['type'] == 'egg' and not guild_dict[guild.id]['raidchannel_dict'][channel.id].get('meetup',{}):
                if (not alreadyexpired):
                    pkmn = guild_dict[guild.id]['raidchannel_dict'][channel.id].get('pokemon', None)
                    if pkmn:
                        await _eggtoraid(pkmn, channel)
                        return
                    maybe_list = []
                    trainer_dict = copy.deepcopy(
                        guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['trainer_dict'])
                    for trainer in trainer_dict.keys():
                        if trainer_dict[trainer]['status']['maybe']:
                            user = channel.guild.get_member(trainer)
                            maybe_list.append(user.mention)
                    h = _('hatched-')
                    new_name = h if h not in channel.name else ''
                    new_name += channel.name
                    await channel.edit(name=new_name)
                    await channel.send(_("**This egg has hatched!**\n\n...or the time has just expired. Trainers {trainer_list}: Update the raid to the pokemon that hatched using **!raid <pokemon>** or reset the hatch timer with **!timerset**. This channel will be deactivated until I get an update and I'll delete it in 45 minutes if I don't hear anything.").format(trainer_list=', '.join(maybe_list)))
                delete_time = (guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp'] + (45 * 60)) - time.time()
                expiremsg = _('**This level {level} raid egg has expired!**').format(
                    level=guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['egglevel'])
            else:
                if (not alreadyexpired):
                    e = _('expired-')
                    new_name = e if e not in channel.name else ''
                    new_name += channel.name
                    await channel.edit(name=new_name)
                    await channel.send(_('This channel timer has expired! The channel has been deactivated and will be deleted in 5 minutes.\nTo reactivate the channel, use **!timerset** to set the timer again.'))
                delete_time = (guild_dict[guild.id]['raidchannel_dict'][channel.id]['exp'] + (5 * 60)) - time.time()
                raidtype = _("event") if guild_dict[guild.id]['raidchannel_dict'][channel.id].get('meetup',False) else _(" raid")
                expiremsg = _('**This {pokemon}{raidtype} has expired!**').format(
                    pokemon=guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['pokemon'].capitalize(), raidtype=raidtype)
            await asyncio.sleep(delete_time)
            # If the channel has already been deleted from the dict, someone
            # else got to it before us, so don't do anything.
            # Also, if the channel got reactivated, don't do anything either.
            try:
                if (guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['active'] == False) and (not Meowth.is_closed()):
                    if dupechannel:
                        try:
                            report_channel = Meowth.get_channel(
                                guild_dict[guild.id]['raidchannel_dict'][channel.id]['reportcity'])
                            reportmsg = await report_channel.get_message(guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['raidreport'])
                            await reportmsg.delete()
                        except:
                            pass
                    else:
                        try:
                            report_channel = Meowth.get_channel(
                                guild_dict[guild.id]['raidchannel_dict'][channel.id]['reportcity'])
                            reportmsg = await report_channel.get_message(guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['raidreport'])
                            await reportmsg.edit(embed=discord.Embed(description=expiremsg, colour=channel.guild.me.colour))
                        except:
                            pass
                    try:
                        report_channel = Meowth.get_channel(
                            guild_dict[guild.id]['raidchannel_dict'][channel.id]['reportcity'])
                        user_message = await report_channel.get_message(guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]['reportmessage'])
                        await user_message.delete()
                    except:
                        pass
                        # channel doesn't exist anymore in serverdict
                    archive = guild_dict[guild.id]['raidchannel_dict'][channel.id].get('archive',False)
                    logs = guild_dict[channel.guild.id]['raidchannel_dict'][channel.id].get('logs', {})
                    channel_exists = Meowth.get_channel(channel.id)
                    if channel_exists == None:
                        return
                    elif not gymhuntrdupe and not archive and not logs:
                        try:
                            del guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]
                        except KeyError:
                            pass
                        await channel_exists.delete()
                        logger.info(
                            'Expire_Channel - Channel Deleted - ' + channel.name)
                    elif gymhuntrdupe and not archive:
                        for overwrite in channel.overwrites:
                            try:
                                await channel.set_permissions(channel.guild.default_role, overwrite=discord.PermissionOverwrite(read_messages=False))
                            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                pass
                            if (overwrite[0].name not in guild.me.top_role.name) and (overwrite[0].name not in guild.me.name):
                                try:
                                    await channel.set_permissions(overwrite[0], read_messages=False)
                                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                    pass
                        await channel.send(_('-----------------------------------------------\n**The channel has been removed from view for everybody but Meowth and server owner to protect from future GymHuntr duplicates. It will be removed on its own, please do not remove it. Just ignore what happens in this channel.**\n-----------------------------------------------'))
                        deltime = ((gymhuntrexp - time.time()) / 60) + 10
                        await _timerset(channel, deltime)
                    elif archive or logs:
                        try:
                            for overwrite in channel.overwrites:
                                if isinstance(overwrite[0], discord.Role):
                                    if overwrite[0].permissions.manage_guild or overwrite[0].permissions.manage_channels:
                                        await channel.set_permissions(overwrite[0], read_messages=True)
                                        continue
                                elif isinstance(overwrite[0], discord.Member):
                                    if channel.permissions_for(overwrite[0]).manage_guild or channel.permissions_for(overwrite[0]).manage_channels:
                                        await channel.set_permissions(overwrite[0], read_messages=True)
                                        continue
                                if (overwrite[0].name not in guild.me.top_role.name) and (overwrite[0].name not in guild.me.name):
                                    await channel.set_permissions(overwrite[0], read_messages=False)
                            for role in guild.role_hierarchy:
                                if role.permissions.manage_guild or role.permissions.manage_channels:
                                    await channel.set_permissions(role, read_messages=True)
                                continue
                            await channel.set_permissions(guild.default_role, read_messages=False)
                        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                            pass
                        new_name = _('archived-')
                        if new_name not in channel.name:
                            new_name += channel.name
                            category = guild_dict[channel.guild.id]['configure_dict'].get('archive', {}).get('category', 'same')
                            if category == 'same':
                                newcat = channel.category
                            else:
                                newcat = channel.guild.get_channel(category)
                            await channel.edit(name=new_name, category=newcat)
                            await channel.send(_('-----------------------------------------------\n**The channel has been archived and removed from view for everybody but Meowth and those with Manage Channel permissions. Any messages that were deleted after the channel was marked for archival will be posted below. You will need to delete this channel manually.**\n-----------------------------------------------'))
                            while logs:
                                earliest = min(logs)
                                embed = discord.Embed(colour=logs[earliest]['color_int'], description=logs[earliest]['content'], timestamp=logs[earliest]['created_at'])
                                if logs[earliest]['author_nick']:
                                    embed.set_author(name="{name} [{nick}]".format(name=logs[earliest]['author_str'],nick=logs[earliest]['author_nick']), icon_url = logs[earliest]['author_avy'])
                                else:
                                    embed.set_author(name=logs[earliest]['author_str'], icon_url = logs[earliest]['author_avy'])
                                await channel.send(embed=embed)
                                del logs[earliest]
                                await asyncio.sleep(.25)
                            del guild_dict[channel.guild.id]['raidchannel_dict'][channel.id]
            except:
                pass


    """Reporting"""

    async def _wild(self, ctx, content, huntr):
        message = ctx.message
        timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        wild_split = huntr.split('|')[0].split()
        del wild_split[0]
        huntrexp = huntr.split('|')[1]
        huntrweather = huntr.split('|')[2]
        huntrexpstamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'], minutes=int(huntrexp.split()[0]), seconds=int(huntrexp.split()[2]))).strftime('%I:%M %p')
        if len(wild_split) <= 1:
            await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**'))
            return
        rgx = '[^a-zA-Z0-9]'
        content = ' '.join(wild_split)
        entered_wild = content.split(' ', 1)[0]
        entered_wild = get_name(entered_wild).lower() if entered_wild.isdigit() else entered_wild.lower()
        wild_details = content.split(' ', 1)[1]
        pkmn_match = next((p for p in ctx.bot.pkmn_info['pokemon_list'] if re.sub(rgx, '', p) == re.sub(rgx, '', entered_wild)), None)
        if (not pkmn_match):
            entered_wild2 = ' '.join([content.split(' ', 2)[0], content.split(' ', 2)[1]]).lower()
            pkmn_match = next((p for p in ctx.bot.pkmn_info['pokemon_list'] if re.sub(rgx, '', p) == re.sub(rgx, '', entered_wild2)), None)
            if pkmn_match:
                entered_wild = entered_wild2
                try:
                    wild_details = content.split(' ', 2)[2]
                except IndexError:
                    await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!wild <pokemon name> <location>**'))
                    return
        if pkmn_match:
            entered_wild = pkmn_match
        else:
            entered_wild = await utils.autocorrect(Meowth, entered_wild, message.channel, message.author)
        if not entered_wild:
            return
        wild = discord.utils.get(message.guild.roles, name=entered_wild)
        if wild is None:
            roletest = ""
        else:
            roletest = _("{pokemon} - ").format(pokemon=wild.mention)
        wild_number = ctx.bot.pkmn_info['pokemon_list'].index(entered_wild) + 1
        wild_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/{0}_.png?cache=0'.format(str(wild_number).zfill(3))
        expiremsg = _('**This {pokemon} has despawned!**').format(pokemon=entered_wild.title())
        wild_gmaps_link = 'https://www.google.com/maps/dir/Current+Location/{0}'.format(wild_details.split("#")[1])
        wild_embed = discord.Embed(title=_('Meowth! Click here for exact directions to the wild {pokemon}!').format(pokemon=entered_wild.title()), url=wild_gmaps_link, colour=message.guild.me.colour)
        wild_embed.add_field(name='**Details:**', value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_wild.title(), pokemonnumber=str(wild_number), type=''.join(utils.get_type(ctx.bot, message.guild, wild_number)), inline=True))
        wild_embed.add_field(name='**Despawns in:**', value=_('{huntrexp} mins ({huntrexpstamp})').format(huntrexp=huntrexp.split()[0], huntrexpstamp=huntrexpstamp), inline=True)
        wild_embed.add_field(name=huntrweather, value=_('Perform a scan to help find more by clicking [here]({huntrurl}).').format(huntrurl=wild_details), inline=False)
        wild_embed.set_thumbnail(url=wild_img_url)
        wild_embed.add_field(name='**Reactions:**', value=_("🏎: I'm on my way!"))
        wild_embed.add_field(name='\u200b', value=_("💨: The Pokemon despawned!"))
        wild_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        despawn = (int(huntrexp.split(' ')[0]) * 60) + int(huntrexp.split(' ')[2])
        wildreportmsg = await message.channel.send(content=_('{roletest}Meowth! Wild {pokemon} reported by {member}! Details: <{location_details}>').format(roletest=roletest,pokemon=entered_wild.title(), member=message.author.mention, location_details=wild_details, gps=wild_details), embed=wild_embed)
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction('🏎')
        await asyncio.sleep(0.25)
        await wildreportmsg.add_reaction('💨')
        await asyncio.sleep(0.25)
        wild_dict = copy.deepcopy(ctx.bot.guild_dict[message.guild.id].get('wildreport_dict',{}))
        wild_dict[wildreportmsg.id] = {
            'exp':time.time() + despawn,
            'expedit': {"content":wildreportmsg.content,"embedcontent":expiremsg},
            'reportmessage':message.id,
            'reportchannel':message.channel.id,
            'reportauthor':message.author.id,
            'location':wild_details,
            'url':wild_gmaps_link,
            'pokemon':entered_wild,
            'omw':[]
        }
        ctx.bot.guild_dict[message.guild.id]['wildreport_dict'] = wild_dict
        wild_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers',{}).setdefault(message.author.id,{}).setdefault('wild_reports',0) + 1
        ctx.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['wild_reports'] = wild_reports

async def _raid(message, content, huntr):
    fromegg = False
    if ctx.bot.guild_dict[message.channel.guild.id]['raidchannel_dict'].get(message.channel.id,{}).get('type') == "egg":
        fromegg = True
    timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
    raid_split = huntr.split("|")[0].split()
    del raid_split[0]
    gymhuntrgps = huntr.split("|")[1]
    gymhuntrmoves = huntr.split("|")[2]
    if len(raid_split) == 0:
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**'))
        return
    if raid_split[0] == 'egg':
        await _raidegg(message, content)
        return
    if fromegg == True:
        eggdetails = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][message.channel.id]
        egglevel = eggdetails['egglevel']
        if raid_split[0].lower() == 'assume':
            if config['allow_assume'][egglevel] == 'False':
                await message.channel.send(_('Meowth! **!raid assume** is not allowed in this level egg.'))
                return
            if ctx.bot.guild_dict[message.channel.guild.id]['raidchannel_dict'][message.channel.id]['active'] == False:
                await _eggtoraid(raid_split[1].lower(), message.channel, message.author)
                return
            else:
                await _eggassume(" ".join(raid_split), message.channel, message.author)
                return
        elif ctx.bot.guild_dict[message.channel.guild.id]['raidchannel_dict'][message.channel.id]['active'] == False:
            await _eggtoraid(" ".join(raid_split).lower(), message.channel, message.author)
            return
        else:
            await message.channel.send(_('Meowth! Please wait until the egg has hatched before changing it to an open raid!'))
            return
    entered_raid = re.sub('[\\@]', '', raid_split[0].lower())
    entered_raid = utils.get_name(Meowth, entered_raid).lower() if entered_raid.isdigit() else entered_raid.lower()
    del raid_split[0]
    if len(raid_split) == 0:
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**'))
        return
    if raid_split[(- 1)].isdigit():
        raidexp = int(raid_split[(- 1)])
        del raid_split[(- 1)]
    elif ':' in raid_split[(- 1)]:
        raid_split[(- 1)] = re.sub('[a-zA-Z]', '', raid_split[(- 1)])
        if raid_split[(- 1)].split(':')[0] == '':
            endhours = 0
        else:
            endhours = int(raid_split[(- 1)].split(':')[0])
        if raid_split[(- 1)].split(':')[1] == '':
            endmins = 0
        else:
            endmins = int(raid_split[(- 1)].split(':')[1])
        raidexp = (60 * endhours) + endmins
        del raid_split[(- 1)]
    else:
        raidexp = False
    rgx = '[^a-zA-Z0-9]'
    pkmn_match = next((p for p in pkmn_info['pokemon_list'] if re.sub(rgx, '', p) == re.sub(rgx, '', entered_raid)), None)
    if pkmn_match:
        entered_raid = pkmn_match
    else:
        entered_raid = await utils.autocorrect(Meowth, entered_raid, message.channel, message.author)
    if not entered_raid:
        return
    raid_match = True if entered_raid in utils.get_raidlist(Meowth) else False
    if (not raid_match):
        await message.channel.send(_('Meowth! The Pokemon {pokemon} does not appear in raids!').format(pokemon=entered_raid.capitalize()))
        return
    elif utils.get_level(Meowth, entered_raid) == "EX":
        await message.channel.send(_("Meowth! The Pokemon {pokemon} only appears in EX Raids! Use **!exraid** to report one!").format(pokemon=entered_raid.capitalize()))
        return
    if raidexp is not False and not huntr:
        if _timercheck(raidexp, raid_info['raid_eggs'][utils.get_level(Meowth, entered_raid)]['raidtime']):
            await message.channel.send(_("Meowth...that's too long. Level {raidlevel} raids currently last no more than {raidtime} minutes...").format(raidlevel=utils.get_level(Meowth, entered_raid), raidtime=raid_info['raid_eggs'][utils.get_level(Meowth, entered_raid)]['raidtime']))
            return
    raid_details = ' '.join(raid_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**'))
        return
    weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                    _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('fog')]
    weather = next((w for w in weather_list if re.sub(rgx, '', w) in re.sub(rgx, '', raid_details.lower())), None)
    if not weather:
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id,{}).get('weather', None)
    raid_details = raid_details.replace(str(weather), '', 1)
    if raid_details == '':
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**'))
        return
    raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(huntr.split("|")[1])
    gyms = utils.get_gyms(Meowth, message.guild.id)
    if gyms:
        match = await utils.gym_match_prompt(Meowth, message.channel, message.author.id, raid_details, gyms)
        gym_info = ""
        if match:
            gym = gyms[match]
            raid_details = match
            gym_coords = gym['coordinates']
            gym_note = gym.get('notes', "")
            gym_alias = gym.get('alias', "")
            if gym_note:
                gym_note = f"**Notes:** {gym_note}"
            if gym_alias:
                raid_details = gym_alias
            raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(gym_coords)
            gym_info = _("**Gym:** {0}\n{1}").format(raid_details, gym_note)
            for raid in ctx.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                raid_address = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['address']
                raid_coords = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['gymhuntrgps']
                raid_reportcity = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['reportcity']
                if (raid_details == raid_address or gym_coords == raid_coords) and message.channel.id == raid_reportcity:
                    return
    else:
        gyms = False
        gym_info = ""
    raid_channel_name = entered_raid + "-" + utils.sanitize_channel_name(raid_details) + "-bot"
    raid_channel_category = utils.get_category(Meowth, message.channel, utils.get_level(Meowth, entered_raid), category_type="raid")
    raid_channel = await message.guild.create_text_channel(raid_channel_name, overwrites=dict(message.channel.overwrites), category=raid_channel_category)
    ow = raid_channel.overwrites_for(raid_channel.guild.default_role)
    ow.send_messages = True
    try:
        await raid_channel.set_permissions(raid_channel.guild.default_role, overwrite = ow)
    except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
        pass
    for role in raid_channel.guild.role_hierarchy:
        if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
            ow = raid_channel.overwrites_for(role)
            ow.manage_channels = True
            ow.manage_messages = True
            ow.manage_roles = True
            try:
                await raid_channel.set_permissions(role, overwrite = ow)
            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                pass
    raid = discord.utils.get(message.guild.roles, name=entered_raid)
    if raid == None:
        roletest = ""
    else:
        roletest = _("{pokemon} - ").format(pokemon=raid.mention)
    raid_number = pkmn_info['pokemon_list'].index(entered_raid) + 1
    raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/{0}_.png?cache=0'.format(str(raid_number).zfill(3))
    raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the raid!'), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
    raid_embed.add_field(name=_('**Details:**'), value=_('{pokemon} ({pokemonnumber}) {type}').format(pokemon=entered_raid.capitalize(), pokemonnumber=str(raid_number), type=''.join(utils.get_type(Meowth, message.guild, raid_number)), inline=True))
    raid_embed.add_field(name=_('**Weaknesses:**'), value=_('{weakness_list}').format(weakness_list=utils.weakness_to_str(Meowth, message.guild, utils.get_weaknesses(Meowth, entered_raid))), inline=True)
    raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
    raid_embed.add_field(name=_('**Expires:**'), value=_('Set with **!timerset**'), inline=True)
    raid_embed.add_field(name=gymhuntrmoves, value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
    raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
    raid_embed.set_thumbnail(url=raid_img_url)
    report_embed = raid_embed
    raidreport = await message.channel.send(content=_('Meowth! {pokemon} raid reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(pokemon=entered_raid.capitalize(), member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=report_embed)
    await asyncio.sleep(1)
    raidmsg = _("{roletest}Meowth! {pokemon} raid reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!\n\nClick the question mark reaction to get help on the commands that work in here.\n\nThis channel will be deleted five minutes after the timer expires.").format(roletest=roletest, pokemon=entered_raid.title(), member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
    raidmessage = await raid_channel.send(content=raidmsg, embed=raid_embed)
    await raidmessage.add_reaction('\u2754')
    await raidmessage.pin()
    level = utils.get_level(Meowth, entered_raid)
    if str(level) in ctx.bot.guild_dict[message.guild.id]['configure_dict']['counters']['auto_levels']:
        try:
            ctrs_dict = await _get_generic_counters(message.guild, entered_raid, weather)
            ctrsmsg = "Here are the best counters for the raid boss in currently known weather conditions! Update weather with **!weather**. If you know the moveset of the boss, you can react to this message with the matching emoji and I will update the counters."
            ctrsmessage = await raid_channel.send(content=ctrsmsg,embed=ctrs_dict[0]['embed'])
            ctrsmessage_id = ctrsmessage.id
            await ctrsmessage.pin()
            for moveset in ctrs_dict:
                await ctrsmessage.add_reaction(ctrs_dict[moveset]['emoji'])
                await asyncio.sleep(0.25)
        except:
            ctrs_dict = {}
            ctrsmessage_id = None
    else:
        ctrs_dict = {}
        ctrsmessage_id = None
    ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
        'reportcity': message.channel.id,
        'trainer_dict': {},
        'exp': time.time() + (60 * raid_info['raid_eggs'][str(level)]['raidtime']),
        'manual_timer': False,
        'active': True,
        'raidmessage': raidmessage.id,
        'raidreport': raidreport.id,
        'reportmessage': message.id,
        'ctrsmessage': ctrsmessage_id,
        'address': raid_details,
        'type': 'raid',
        'pokemon': entered_raid,
        'egglevel': '0',
        'ctrs_dict': ctrs_dict,
        'moveset': 0,
        'weather': weather,
        'gymhuntrgps' : gymhuntrgps
    }
    if raidexp is not False:
        await _timerset(raid_channel, raidexp)
    else:
        await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left on the raid using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
    await raid_channel.send("This raid was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
    event_loop.create_task(self.expiry_check(raid_channel))
    raid_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers',{}).setdefault(message.author.id,{}).setdefault('raid_reports',0) + 1
    ctx.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['raid_reports'] = raid_reports
    return raid_channel

async def _raidegg(message, content, huntr):
    timestamp = (message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
    raidexp = False
    hourminute = False
    raidegg_split = huntr.split("|")[0].split()
    del raidegg_split[0]
    gymhuntrgps = huntr.split("|")[1]
    if raidegg_split[0].lower() == 'egg':
        del raidegg_split[0]
    if len(raidegg_split) <= 1:
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raidegg <level> <location>**'))
        return
    if raidegg_split[0].isdigit():
        egg_level = int(raidegg_split[0])
        del raidegg_split[0]
    else:
        await message.channel.send(_('Meowth! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info.'))
        return
    if raidegg_split[(- 1)].isdigit():
        raidexp = int(raidegg_split[(- 1)])
        del raidegg_split[(- 1)]
    elif ':' in raidegg_split[(- 1)]:
        msg = _("Did you mean egg hatch time {0} or time remaining before hatch {1}?").format("🥚", "⏲")
        question = await message.channel.send(msg)
        try:
            timeout = False
            res, reactuser = await utils.ask(Meowth, question, message.author.id, react_list=['🥚', '⏲'])
        except TypeError:
            timeout = True
        await question.delete()
        if timeout or res.emoji == '⏲':
            hourminute = True
        elif res.emoji == '🥚':
            now = datetime.datetime.utcnow() + datetime.timedelta(hours=ctx.bot.guild_dict[message.channel.guild.id]['configure_dict']['settings']['offset'])
            start = dateparser.parse(raidegg_split[(- 1)], settings={'PREFER_DATES_FROM': 'future'})
            if start.day != now.day:
                if "m" not in raidegg_split[(- 1)]:
                    start = start + datetime.timedelta(hours=12)
                start = start.replace(day=now.day)
            timediff = relativedelta(start, now)
            raidexp = (timediff.hours*60) + timediff.minutes + 1
            if raidexp < 0:
                await message.channel.send(_('Meowth! Please enter a time in the future.'))
                return
            del raidegg_split[(- 1)]
    if hourminute:
        (h, m) = re.sub('[a-zA-Z]', '', raidegg_split[(- 1)]).split(':', maxsplit=1)
        if h == '':
            h = '0'
        if m == '':
            m = '0'
        if h.isdigit() and m.isdigit():
            raidexp = (60 * int(h)) + int(m)
        del raidegg_split[(- 1)]
    if raidexp is not False and not huntr:
        if _timercheck(raidexp, raid_info['raid_eggs'][str(egg_level)]['hatchtime']):
            await message.channel.send(_("Meowth...that's too long. Level {raidlevel} Raid Eggs currently last no more than {hatchtime} minutes...").format(raidlevel=egg_level, hatchtime=raid_info['raid_eggs'][str(egg_level)]['hatchtime']))
            return
    raid_details = ' '.join(raidegg_split)
    raid_details = raid_details.strip()
    if raid_details == '':
        await message.channel.send(_('Meowth! Give more details when reporting! Use at least: **!raidegg <level> <location>**. Type **!help** raidegg for more info.'))
        return
    rgx = '[^a-zA-Z0-9]'
    weather_list = [_('none'), _('extreme'), _('clear'), _('sunny'), _('rainy'),
                    _('partlycloudy'), _('cloudy'), _('windy'), _('snow'), _('fog')]
    weather = next((w for w in weather_list if re.sub(rgx, '', w) in re.sub(rgx, '', raid_details.lower())), None)
    raid_details = raid_details.replace(str(weather), '', 1)
    if not weather:
        weather = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'].get(message.channel.id,{}).get('weather', None)
    if raid_details == '':
        await message.channel.send(_('Meowth! Give more details when reporting! Usage: **!raid <pokemon name> <location>**'))
        return
    raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(huntr.split("|")[1])
    gyms = utils.get_gyms(Meowth, message.guild.id)
    if gyms:
        match = await utils.gym_match_prompt(Meowth, message.channel, message.author.id, raid_details, gyms)
        gym_info = ""
        if match:
            gym = gyms[match]
            raid_details = match
            gym_coords = gym['coordinates']
            gym_note = gym.get('notes', "")
            gym_alias = gym.get('alias', "")
            if gym_note:
                gym_note = f"**Notes:** {gym_note}"
            if gym_alias:
                raid_details = gym_alias
            raid_gmaps_link = "https://www.google.com/maps/dir/Current+Location/{0}".format(gym_coords)
            gym_info = _("**Gym:** {0}\n{1}").format(raid_details, gym_note)
            for raid in ctx.bot.guild_dict[message.guild.id]['raidchannel_dict']:
                raid_address = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['address']
                raid_coords = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['gymhuntrgps']
                raid_reportcity = ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid]['reportcity']
                if (raid_details == raid_address or gym_coords == raid_coords) and message.channel.id == raid_reportcity:
                    return
    else:
        gyms = False
        gym_info = ""
    if (egg_level > 5) or (egg_level == 0):
        await message.channel.send(_('Meowth! Raid egg levels are only from 1-5!'))
        return
    else:
        egg_level = str(egg_level)
        egg_info = raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_list = []
        for p in egg_info['pokemon']:
            p_name = utils.get_name(Meowth, p).title()
            p_type = utils.get_type(Meowth, message.guild, p)
            boss_list.append((((p_name + ' (') + str(p)) + ') ') + ''.join(p_type))
        if not huntr:
            raid_channel_name = _('level-{egg_level}-egg-').format(egg_level=egg_level)
            raid_channel_name += utils.sanitize_channel_name(raid_details)
        else:
            raid_channel_name = _('level-{egg_level}-egg-').format(egg_level=egg_level)
            raid_channel_name += utils.sanitize_channel_name(raid_details) + "-bot"
        raid_channel_category = utils.get_category(Meowth, message.channel, egg_level, category_type="raid")
        raid_channel = await message.guild.create_text_channel(raid_channel_name, overwrites=dict(message.channel.overwrites), category=raid_channel_category)
        ow = raid_channel.overwrites_for(raid_channel.guild.default_role)
        ow.send_messages = True
        try:
            await raid_channel.set_permissions(raid_channel.guild.default_role, overwrite = ow)
        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
            pass
        for role in raid_channel.guild.role_hierarchy:
            if role.permissions.manage_guild or role.permissions.manage_channels or role.permissions.manage_messages:
                ow = raid_channel.overwrites_for(role)
                ow.manage_channels = True
                ow.manage_messages = True
                ow.manage_roles = True
                try:
                    await raid_channel.set_permissions(role, overwrite = ow)
                except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                    pass
        raid_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{}?cache=0'.format(str(egg_img))
        raid_embed = discord.Embed(title=_('Meowth! Click here for directions to the coming raid!'), description=gym_info, url=raid_gmaps_link, colour=message.guild.me.colour)
        if len(egg_info['pokemon']) > 1:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist1}').format(bosslist1='\n'.join(boss_list[::2])), inline=True)
            raid_embed.add_field(name='\u200b', value=_('{bosslist2}').format(bosslist2='\n'.join(boss_list[1::2])), inline=True)
        else:
            raid_embed.add_field(name=_('**Possible Bosses:**'), value=_('{bosslist}').format(bosslist=''.join(boss_list)), inline=True)
            raid_embed.add_field(name='\u200b', value='\u200b', inline=True)
        raid_embed.add_field(name=_('**Next Group:**'), value=_('Set with **!starttime**'), inline=True)
        raid_embed.add_field(name=_('**Hatches:**'), value=_('Set with **!timerset**'), inline=True)
        raid_embed.add_field(name="\u200b", value=_("Perform a scan to help find more by clicking [here](https://gymhuntr.com/#{huntrurl}).").format(huntrurl=gymhuntrgps), inline=False)
        raid_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=message.author.display_name, timestamp=timestamp), icon_url=message.author.avatar_url_as(format=None, static_format='jpg', size=32))
        raid_embed.set_thumbnail(url=raid_img_url)
        raidreport = await message.channel.send(content=_('Meowth! Level {level} raid egg reported by {member}! Details: {location_details}. Coordinate in {raid_channel}').format(level=egg_level, member=message.author.mention, location_details=raid_details, raid_channel=raid_channel.mention), embed=raid_embed)
        await asyncio.sleep(1)
        raidmsg = _("Meowth! Level {level} raid egg reported by {member} in {citychannel}! Details: {location_details}. Coordinate here!\n\nClick the question mark reaction to get help on the commands that work in here.\n\nThis channel will be deleted five minutes after the timer expires.").format(level=egg_level, member=message.author.mention, citychannel=message.channel.mention, location_details=raid_details)
        raidmessage = await raid_channel.send(content=raidmsg, embed=raid_embed)
        await raidmessage.add_reaction('\u2754')
        await raidmessage.pin()
        ctx.bot.guild_dict[message.guild.id]['raidchannel_dict'][raid_channel.id] = {
            'reportcity': message.channel.id,
            'trainer_dict': {

            },
            'exp': time.time() + (60 * raid_info['raid_eggs'][egg_level]['hatchtime']),
            'manual_timer': False,
            'active': True,
            'raidmessage': raidmessage.id,
            'raidreport': raidreport.id,
            'reportmessage': message.id,
            'address': raid_details,
            'type': 'egg',
            'pokemon': '',
            'egglevel': egg_level,
            'weather': weather,
            'moveset': 0,
            'gymhuntrgps' : gymhuntrgps
        }
        if raidexp is not False:
            await _timerset(raid_channel, raidexp)
        else:
            await raid_channel.send(content=_('Meowth! Hey {member}, if you can, set the time left until the egg hatches using **!timerset <minutes>** so others can check it with **!timer**.').format(member=message.author.mention))
        await raid_channel.send("This egg was reported by a bot. If it is a duplicate of a raid already reported by a human, I can delete it with three **!duplicate** messages.")
        if len(raid_info['raid_eggs'][egg_level]['pokemon']) == 1:
            await _eggassume('assume ' + utils.get_name(Meowth, raid_info['raid_eggs'][egg_level]['pokemon'][0]), raid_channel)
        elif egg_level == "5" and ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings'].get('regional',None) in raid_info['raid_eggs']["5"]['pokemon']:
            await _eggassume('assume ' + utils.get_name(Meowth, ctx.bot.guild_dict[raid_channel.guild.id]['configure_dict']['settings']['regional']), raid_channel)
        event_loop.create_task(self.expiry_check(raid_channel))
        egg_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers',{}).setdefault(message.author.id,{}).setdefault('egg_reports',0) + 1
        ctx.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['egg_reports'] = egg_reports
















    @commands.command()
    async def huntrraid(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
        description = "**Marilla Park.**\nMewtwo\n**CP:** 60540 - **Moves:** Confusion / Shadow Ball\n*Raid Ending: 0 hours 46 min 50 sec*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=0'
        huntrembed = discord.Embed(title=_('Level 5 Raid has started!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command()
    async def huntregg(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
        description = "**Marilla Park.**\n*Raid Starting: 0 hours 46 min 50 sec*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/5.png?cache=0'
        huntrembed = discord.Embed(title=_('Level 5 Raid is starting soon!!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

    @commands.command()
    async def huntrwild(self, ctx):
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        await message.delete()
        description = "Click above to view the wild\n\n*Remaining: 25 min 3 sec*\nWeather: *None*"
        url = "https://gymhuntr.com/#34.008618,-118.49125"
        img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/150_.png?cache=0'
        huntrembed = discord.Embed(title=_('A wild Mewtwo (150) has appeared!'), description=description, url=url, colour=message.guild.me.colour)
        huntrembed.set_thumbnail(url=img_url)
        huntrmessage = await ctx.channel.send(embed=huntrembed)
        ctx = await self.bot.get_context(huntrmessage)
        await self.on_huntr(ctx)

def setup(bot):
    bot.add_cog(Huntr(bot))

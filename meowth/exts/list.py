import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging
import string
from operator import itemgetter

import discord
from discord.ext import commands

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Listing(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="list", aliases=['lists', 'tag', 'l'], case_insensitive=True)
    @checks.guildchannel()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def _list(self, ctx):
        """Lists all info for the current channel depending on channel type.

        Usage: !list
        Works only in raid or city channels. Calls the interested, waiting, and here lists. Also prints
        the raid timer. In city channels, lists all active raids."""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'tag']:
            await utils.safe_delete(ctx.message)
        if ctx.invoked_subcommand == None:
            async with ctx.typing():
                listmsg = _('**Meowth!** ')
                temp_list = ""
                raid_list = ""
                guild = ctx.guild
                channel = ctx.channel
                now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
                list_messages = []
                raid_cog = self.bot.cogs.get('Raid')
                if (checks.check_raidreport(ctx) or checks.check_exraidreport(ctx) or checks.check_meetupreport(ctx)):
                    if not raid_cog:
                        return
                    if str(ctx.invoked_with).lower() == "tag":
                        tag_error = await channel.send(f"Please use **{ctx.prefix}{ctx.invoked_with}** in an active raid channel.", delete_after=10)
                        await asyncio.sleep(10)
                        await utils.safe_delete(ctx.message)
                        await utils.safe_delete(tag_error)
                        return
                    cty = channel.name
                    rc_d = {**self.bot.guild_dict[guild.id]['raidchannel_dict'], **self.bot.guild_dict[guild.id]['meetup_dict']}
                    raid_dict = {}
                    egg_dict = {}
                    exraid_list = []
                    event_list = []
                    list_dict = self.bot.guild_dict[guild.id].setdefault('list_dict', {}).setdefault('raid', {}).setdefault(ctx.channel.id, [])
                    delete_list = []
                    for msg in list_dict:
                        try:
                            msg = await ctx.channel.fetch_message(msg)
                            delete_list.append(msg)
                        except:
                            pass
                    await utils.safe_bulk_delete(ctx.channel, delete_list)
                    for r in rc_d:
                        report_channel = self.bot.get_channel(rc_d[r]['report_channel'])
                        if not report_channel:
                            continue
                        if (report_channel.name == cty) and rc_d[r]['active'] and discord.utils.get(guild.text_channels, id=r):
                            exp = rc_d[r]['exp']
                            type = rc_d[r]['type']
                            level = rc_d[r]['egg_level']
                            if (type == 'egg') and level.isdigit():
                                egg_dict[r] = exp
                            elif rc_d[r].get('meetup', {}):
                                event_list.append(r)
                            elif ((type == 'exraid') or (level == 'EX')):
                                exraid_list.append(r)
                            else:
                                raid_dict[r] = exp

                    async def list_output(r):
                        trainer_dict = rc_d[r]['trainer_dict']
                        rchan = self.bot.get_channel(r)
                        end = datetime.datetime.utcfromtimestamp(rc_d[r]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
                        output = ''
                        start_str = ''
                        channel_dict, boss_dict = await raid_cog._get_party(rchan)
                        if not channel_dict['total'] and "all" not in ctx.message.content.lower():
                            return None
                        if rc_d[r]['manual_timer'] == False:
                            assumed_str = _(' (assumed)')
                        else:
                            assumed_str = ''
                        if channel_dict.get('train', False):
                            train_str = "{train_emoji} - ".format(train_emoji=self.bot.custom_emoji.get('train_emoji', '\U0001F682'))
                        else:
                            train_str = ''
                        starttime = rc_d[r].get('starttime', None)
                        meetup = rc_d[r].get('meetup', {})
                        if starttime and starttime > now and not meetup:
                            start_str = _('\nNext group: **{}**').format(starttime.strftime(_('%I:%M %p (%H:%M)')))
                        else:
                            starttime = False
                        if rc_d[r]['egg_level'].isdigit() and (int(rc_d[r]['egg_level']) > 0):
                            expirytext = _(' - {train_str}Hatches: {expiry}{is_assumed}').format(train_str=train_str, expiry=end.strftime(_('%I:%M %p (%H:%M)')), is_assumed=assumed_str)
                        elif ((rc_d[r]['egg_level'] == 'EX') or (rc_d[r]['type'] == 'exraid')) and not meetup:
                            expirytext = _(' - {train_str}Hatches: {expiry}{is_assumed}').format(train_str=train_str, expiry=end.strftime(_('%B %d at %I:%M %p (%H:%M)')), is_assumed=assumed_str)
                        elif meetup:
                            meetupstart = meetup['start']
                            meetupend = meetup['end']
                            expirytext = ""
                            if meetupstart:
                                expirytext += _(' - Starts: {expiry}{is_assumed}').format(expiry=meetupstart.strftime(_('%B %d at %I:%M %p (%H:%M)')), is_assumed=assumed_str)
                            if meetupend:
                                expirytext += _(" - Ends: {expiry}{is_assumed}").format(expiry=meetupend.strftime(_('%B %d at %I:%M %p (%H:%M)')), is_assumed=assumed_str)
                            if not meetupstart and not meetupend:
                                expirytext = _(' - Starts: {expiry}{is_assumed}').format(expiry=end.strftime(_('%B %d at %I:%M %p (%H:%M)')), is_assumed=assumed_str)
                        else:
                            type_str = ""
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, rc_d[r].get('pkmn_obj', ""))
                            if pokemon:
                                type_str = pokemon.emoji
                            expirytext = _('{type_str} - {train_str}Expires: {expiry}{is_assumed}').format(type_str=type_str, train_str=train_str, expiry=end.strftime(_('%I:%M %p (%H:%M)')), is_assumed=assumed_str)
                        output += f"{rchan.mention}{expirytext}"
                        if channel_dict['total']:
                            output += f"\n**Total: {channel_dict['total']}**"
                        if channel_dict['maybe']:
                            output += f" | Maybe: **{channel_dict['maybe']}**"
                        if channel_dict['coming']:
                            output += f" | Coming: **{channel_dict['coming']}**"
                        if channel_dict['here']:
                            output += f" | Here: **{channel_dict['here']}**"
                        if channel_dict['lobby']:
                            output += f" | Lobby: **{channel_dict['lobby']}**"
                        if channel_dict['mystic']:
                            emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['mystic'])
                            output += f" | {emoji}: **{channel_dict['mystic']}**"
                        if channel_dict['valor']:
                            emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['valor'])
                            output += f" | {emoji}: **{channel_dict['valor']}**"
                        if channel_dict['instinct']:
                            emoji = utils.parse_emoji(channel.guild, self.bot.config.team_dict['instinct'])
                            output += f" | {emoji}: **{channel_dict['instinct']}**"
                        if channel_dict['unknown']:
                            emoji = utils.parse_emoji(channel.guild, self.bot.config.unknown)
                            output += f" | {emoji}: **{channel_dict['unknown']}**"
                        if start_str:
                            output += f"{start_str}\n"
                        else:
                            output += f"\n"
                        return output

                    if raid_dict:
                        for (r, e) in sorted(raid_dict.items(), key=itemgetter(1)):
                            output = await list_output(r)
                            if output:
                                temp_list += output
                        if temp_list:
                            raid_list += f"**Raids:**\n{temp_list}\n"
                            temp_list = ""
                    if egg_dict:
                        for (r, e) in sorted(egg_dict.items(), key=itemgetter(1)):
                            output = await list_output(r)
                            if output:
                                temp_list += output
                        if temp_list:
                            raid_list += f"**Raid Eggs:**\n{temp_list}\n"
                            temp_list = ""
                    if exraid_list:
                        for r in exraid_list:
                            output = await list_output(r)
                            if output:
                                temp_list += output
                        if temp_list:
                            raid_list += f"**EX Raids:**\n{temp_list}\n"
                            temp_list = ""
                    if event_list:
                        for r in event_list:
                            output = await list_output(r)
                            if output:
                                temp_list += output
                        if temp_list:
                            raid_list += f"**Meetups:**\n{temp_list}\n"
                            temp_list = ""

                    if not raid_list:
                        if "all" not in ctx.message.content.lower():
                            ctx.message.content = "!list all"
                            await ctx.reinvoke()
                            return
                        list_message = await channel.send(f"Meowth! No active channels!", embed=discord.Embed(colour=ctx.guild.me.colour, description=_('Report a new one with **!raid <name> <location> [weather] [timer]**')))
                        list_messages.append(list_message.id)
                    else:
                        listmsg += _("**Here's the current channels for {0}**\n\n").format(channel.mention)
                        paginator = commands.Paginator(prefix="", suffix="")
                        index = 0
                        for line in raid_list.splitlines():
                            paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                        for p in paginator.pages:
                            if index == 0:
                                list_message = await ctx.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                            else:
                                list_message = await ctx.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                            list_messages.append(list_message.id)
                            index += 1
                    self.bot.guild_dict[ctx.guild.id]['list_dict']['raid'][ctx.channel.id] = list_messages

                elif checks.check_rsvpchannel(ctx):
                    report_dict = await utils.get_report_dict(self.bot, ctx.channel)
                    if not raid_cog:
                        return
                    team_list = ["mystic", "valor", "instinct", "unknown"]
                    tag = False
                    team = False
                    list_messages = []
                    if str(ctx.invoked_with).lower() == "tag":
                        tag = True
                    starttime = self.bot.guild_dict[guild.id][report_dict][channel.id].get('starttime', None)
                    meetup = self.bot.guild_dict[guild.id][report_dict][channel.id].get('meetup', {})
                    raid_message = self.bot.guild_dict[guild.id][report_dict][channel.id]['raid_message']
                    try:
                        raid_message = await channel.fetch_message(raid_message)
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        raid_message = None
                    rc_d = self.bot.guild_dict[guild.id][report_dict][channel.id]
                    list_split = ctx.message.clean_content.lower().split()
                    list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('raid', {}).setdefault(ctx.channel.id, [])
                    delete_list = []
                    for msg in list_dict:
                        try:
                            msg = await ctx.channel.fetch_message(msg)
                            delete_list.append(msg)
                        except:
                            pass
                    await utils.safe_bulk_delete(ctx.channel, delete_list)
                    if "tags" in list_split or "tag" in list_split:
                        tag = True
                    for word in list_split:
                        if word in team_list:
                            team = word.lower()
                            break
                    if team == "mystic" or team == "valor" or team == "instinct":
                        bulletpoint = utils.parse_emoji(ctx.guild, self.bot.config.team_dict[team])
                    elif team == "unknown":
                        bulletpoint = utils.parse_emoji(ctx.guild, self.bot.config.unknown)
                    else:
                        bulletpoint = self.bot.custom_emoji.get('bullet', '\U0001F539')
                    if " 0 interested!" not in await self._interest(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._interest(ctx, tag, team))
                    if " 0 on the way!" not in await self._otw(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._otw(ctx, tag, team))
                    if " 0 waiting at the raid!" not in await self._waiting(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._waiting(ctx, tag, team))
                    if " 0 in the lobby!" not in await self._lobbylist(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._lobbylist(ctx, tag, team))
                    if (len(listmsg.splitlines()) <= 1):
                        listmsg +=  ('\n' + bulletpoint) + (_(" Nobody has updated their status yet!"))
                    listmsg += ('\n' + bulletpoint) + (await raid_cog.print_raid_timer(channel))
                    if starttime and (starttime > now) and not meetup:
                        listmsg += _('\nThe next group will be starting at **{}**').format(starttime.strftime(_('%I:%M %p (%H:%M)')))
                    if raid_message:
                        list_embed = discord.Embed(colour=ctx.guild.me.colour, description=listmsg, title=raid_message.embeds[0].title, url=raid_message.embeds[0].url)
                        if len(raid_message.embeds[0].fields) > 4:
                            for field in raid_message.embeds[0].fields:
                                if "status" in field.name.lower() or "team" in field.name.lower():
                                    list_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                    else:
                        list_embed = discord.Embed(colour=ctx.guild.me.colour, description=listmsg)
                    if tag:
                        list_msg = await ctx.channel.send(listmsg)
                    else:
                        list_msg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(list_msg.id)
                    self.bot.guild_dict[guild.id].setdefault('list_dict', {}).setdefault('raid', {})[channel.id] = list_messages
                    return
                elif checks.check_wantchannel(ctx):
                    if not (checks.check_wildreport(ctx) or checks.check_nestreport(ctx) or checks.check_researchreport(ctx) or checks.check_tradereport(ctx) or checks.check_lurereport(ctx) or checks.check_pvpreport(ctx)):
                        want_command = ctx.command.all_commands.get('wants')
                        if want_command:
                            await want_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_researchreport(ctx):
                    if not (checks.check_wildreport(ctx) or checks.check_nestreport(ctx) or checks.check_wantchannel(ctx) or checks.check_tradereport(ctx) or checks.check_lurereport(ctx) or checks.check_pvpreport(ctx)):
                        research_command = ctx.command.all_commands.get('research')
                        if research_command:
                            await research_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_wildreport(ctx):
                    if not (checks.check_researchreport(ctx) or checks.check_nestreport(ctx) or checks.check_wantchannel(ctx) or checks.check_tradereport(ctx) or checks.check_lurereport(ctx) or checks.check_pvpreport(ctx)):
                        wild_command = ctx.command.all_commands.get('wild')
                        if wild_command:
                            await wild_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_nestreport(ctx):
                    if not (checks.check_researchreport(ctx) or checks.check_wildreport(ctx) or checks.check_wantchannel(ctx) or checks.check_tradereport(ctx) or checks.check_lurereport(ctx) or checks.check_pvpreport(ctx)):
                        nest_command = ctx.command.all_commands.get('nest')
                        if nest_command:
                            await nest_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_tradereport(ctx):
                    if not (checks.check_researchreport(ctx) or checks.check_wildreport(ctx) or checks.check_wantchannel(ctx) or checks.check_nestreport(ctx) or checks.check_lurereport(ctx) or checks.check_pvpreport(ctx)):
                        trade_command = ctx.command.all_commands.get('trades')
                        if trade_command:
                            await trade_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_lurereport(ctx):
                    if not (checks.check_researchreport(ctx) or checks.check_wildreport(ctx) or checks.check_wantchannel(ctx) or checks.check_nestreport(ctx) or checks.check_tradereport(ctx) or checks.check_pvpreport(ctx)):
                        trade_command = ctx.command.all_commands.get('lures')
                        if trade_command:
                            await trade_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                elif checks.check_pvpreport(ctx):
                    if not (checks.check_researchreport(ctx) or checks.check_wildreport(ctx) or checks.check_wantchannel(ctx) or checks.check_nestreport(ctx) or checks.check_tradereport(ctx) or checks.check_lurereport(ctx)):
                        trade_command = ctx.command.all_commands.get('pvp')
                        if trade_command:
                            await trade_command.invoke(ctx)
                    else:
                        await ctx.send("**Meowth!** I don't know what list you wanted. Try **!list research, !list wilds, !list wants, !list nests, !list lures, !list pvp, or !list trades**", delete_after=10)
                        return
                else:
                    raise checks.errors.CityRaidChannelCheckFail()

    @_list.command()
    @checks.rsvpchannel()
    async def interested(self, ctx, tags: str = ''):
        """Lists the number and users who are interested in the raid.

        Usage: !list interested
        Works only in raid channels."""
        listmsg = _('**Meowth!**\n')
        if tags and tags.lower() == "tags" or tags.lower() == "tag":
            tags = True
        async with ctx.typing():
            listmsg += await self._interest(ctx, tags)
            if tags:
                await ctx.channel.send(listmsg)
            else:
                await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _interest(self, ctx, tag=False, team=False):
        ctx_maybecount = 0
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
        maybe_exstr = ''
        maybe_list = []
        name_list = []
        for trainer in trainer_dict.keys():
            user = ctx.guild.get_member(trainer)
            if (trainer_dict[trainer]['status']['maybe']) and user and team == False:
                ctx_maybecount += trainer_dict[trainer]['status']['maybe']
                if trainer_dict[trainer]['status']['maybe'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    maybe_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['status']['maybe']))
                    maybe_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['status']['maybe']))
            elif (trainer_dict[trainer]['status']['maybe']) and user and team and trainer_dict[trainer]['party'][team]:
                if trainer_dict[trainer]['status']['maybe'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    maybe_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['party'][team]))
                    maybe_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['party'][team]))
                ctx_maybecount += trainer_dict[trainer]['party'][team]

        if ctx_maybecount > 0:
            if (now.time() >= datetime.time(5, 0)) and (now.time() <= datetime.time(21, 0)) and (tag == True):
                maybe_exstr = _(' including {trainer_list} and the people with them! Let them know if there is a group forming').format(trainer_list=', '.join(maybe_list))
            else:
                maybe_exstr = _(' including {trainer_list} and the people with them! Let them know if there is a group forming').format(trainer_list=', '.join(name_list))
        listmsg = _(' {trainer_count} interested{including_string}!').format(trainer_count=str(ctx_maybecount), including_string=maybe_exstr)
        return listmsg

    @_list.command()
    @checks.rsvpchannel()
    async def coming(self, ctx, tags: str = ''):
        """Lists the number and users who are coming to a raid.

        Usage: !list coming
        Works only in raid channels."""
        listmsg = _('**Meowth!**\n')
        if tags and tags.lower() == "tags" or tags.lower() == "tag":
            tags = True
        async with ctx.typing():
            listmsg += await self._otw(ctx, tags)
            if tags:
                await ctx.channel.send(listmsg)
            else:
                await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _otw(self, ctx, tag=False, team=False):
        ctx_comingcount = 0
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
        otw_exstr = ''
        otw_list = []
        name_list = []
        for trainer in trainer_dict.keys():
            user = ctx.guild.get_member(trainer)
            if (trainer_dict[trainer]['status']['coming']) and user and team == False:
                ctx_comingcount += trainer_dict[trainer]['status']['coming']
                if trainer_dict[trainer]['status']['coming'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    otw_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['status']['coming']))
                    otw_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['status']['coming']))
            elif (trainer_dict[trainer]['status']['coming']) and user and team and trainer_dict[trainer]['party'][team]:
                if trainer_dict[trainer]['status']['coming'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    otw_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['party'][team]))
                    otw_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['party'][team]))
                ctx_comingcount += trainer_dict[trainer]['party'][team]

        if ctx_comingcount > 0:
            if (now.time() >= datetime.time(5, 0)) and (now.time() <= datetime.time(21, 0)) and (tag == True):
                otw_exstr = _(' including {trainer_list} and the people with them! Be considerate and wait for them if possible').format(trainer_list=', '.join(otw_list))
            else:
                otw_exstr = _(' including {trainer_list} and the people with them! Be considerate and wait for them if possible').format(trainer_list=', '.join(name_list))
        listmsg = _(' {trainer_count} on the way{including_string}!').format(trainer_count=str(ctx_comingcount), including_string=otw_exstr)
        return listmsg

    @_list.command()
    @checks.rsvpchannel()
    async def here(self, ctx, tags: str = ''):
        """List the number and users who are present at a raid.

        Usage: !list here
        Works only in raid channels."""
        listmsg = _('**Meowth!**\n')
        if tags and tags.lower() == "tags" or tags.lower() == "tag":
            tags = True
        async with ctx.typing():
            listmsg += await self._waiting(ctx, tags)
            if tags:
                await ctx.channel.send(listmsg)
            else:
                await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _waiting(self, ctx, tag=False, team=False):
        ctx_herecount = 0
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        raid_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id])
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
        here_exstr = ''
        here_list = []
        name_list = []
        for trainer in trainer_dict.keys():
            user = ctx.guild.get_member(trainer)
            if (trainer_dict[trainer]['status']['here']) and user and team == False:
                ctx_herecount += trainer_dict[trainer]['status']['here']
                if trainer_dict[trainer]['status']['here'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    here_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['status']['here']))
                    here_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['status']['here']))
            elif (trainer_dict[trainer]['status']['here']) and user and team and trainer_dict[trainer]['party'][team]:
                if trainer_dict[trainer]['status']['here'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    here_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['party'][team]))
                    here_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['party'][team]))
                ctx_herecount += trainer_dict[trainer]['party'][team]
                if raid_dict.get('lobby', {"team":"all"})['team'] == team or raid_dict.get('lobby', {"team":"all"})['team'] == "all":
                    ctx_herecount -= trainer_dict[trainer]['status']['lobby']
        raidtype = _("event") if self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id].get('meetup', False) else _("raid")
        if ctx_herecount > 0:
            if (now.time() >= datetime.time(5, 0)) and (now.time() <= datetime.time(21, 0)) and (tag == True):
                here_exstr = _(" including {trainer_list} and the people with them! Be considerate and let them know if and when you'll be there").format(trainer_list=', '.join(here_list))
            else:
                here_exstr = _(" including {trainer_list} and the people with them! Be considerate and let them know if and when you'll be there").format(trainer_list=', '.join(name_list))
        listmsg = _(' {trainer_count} waiting at the {raidtype}{including_string}!').format(trainer_count=str(ctx_herecount), raidtype=raidtype, including_string=here_exstr)
        return listmsg

    @_list.command()
    @checks.activeraidchannel()
    async def lobby(self, ctx, tags: str = ''):
        """List the number and users who are in the raid lobby.

        Usage: !list lobby
        Works only in raid channels."""
        listmsg = _('**Meowth!**\n')
        if tags and tags.lower() == "tags" or tags.lower() == "tag":
            tags = True
        async with ctx.typing():
            listmsg += await self._lobbylist(ctx, tags)
            if tags:
                await ctx.channel.send(listmsg)
            else:
                await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _lobbylist(self, ctx, tag=False, team=False):
        ctx_lobbycount = 0
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        raid_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id])
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['trainer_dict'])
        lobby_exstr = ''
        lobby_list = []
        name_list = []
        for trainer in trainer_dict.keys():
            user = ctx.guild.get_member(trainer)
            if (trainer_dict[trainer]['status']['lobby']) and user and team == False:
                ctx_lobbycount += trainer_dict[trainer]['status']['lobby']
                if trainer_dict[trainer]['status']['lobby'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    lobby_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['status']['lobby']))
                    lobby_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['status']['lobby']))
            elif (trainer_dict[trainer]['status']['lobby']) and user and team and trainer_dict[trainer]['party'][team]:
                if trainer_dict[trainer]['status']['lobby'] == 1:
                    name_list.append(_('**{name}**').format(name=user.display_name))
                    lobby_list.append(user.mention)
                else:
                    name_list.append(_('**{name} ({count})**').format(name=user.display_name, count=trainer_dict[trainer]['party'][team]))
                    lobby_list.append(_('{name} **({count})**').format(name=user.mention, count=trainer_dict[trainer]['party'][team]))
                if raid_dict.get('lobby', {"team":"all"})['team'] == team or raid_dict.get('lobby', {"team":"all"})['team'] == "all":
                    ctx_lobbycount += trainer_dict[trainer]['party'][team]

        if ctx_lobbycount > 0:
            if (now.time() >= datetime.time(5, 0)) and (now.time() <= datetime.time(21, 0)) and (tag == True):
                lobby_exstr = _(' including {trainer_list} and the people with them! Use **!lobby** if you are joining them or **!backout** to request a backout').format(trainer_list=', '.join(lobby_list))
            else:
                lobby_exstr = _(' including {trainer_list} and the people with them! Use **!lobby** if you are joining them or **!backout** to request a backout').format(trainer_list=', '.join(name_list))
        listmsg = _(' {trainer_count} in the lobby{including_string}!').format(trainer_count=str(ctx_lobbycount), including_string=lobby_exstr)
        return listmsg

    @_list.command()
    @checks.activeraidchannel()
    async def groups(self, ctx):
        """List the users in lobby, active raids, completed raids.

        Usage: !list groups
        Works only in raid channels."""
        ctx_lobbycount = 0
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict']['settings']['offset'])
        raid_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id])
        raid_lobby = raid_dict.get("lobby", None)
        raid_active = raid_dict.get("battling", None)
        raid_complete = raid_dict.get("completed", None)
        list_embed = discord.Embed(colour=ctx.guild.me.colour)
        lobby_str = ""
        active_str = ""
        complete_str = ""
        all_lobbies = []
        index = 0
        await utils.safe_delete(ctx.message)
        async with ctx.typing():
            if raid_lobby:
                lobby_str = f"**{index}.** "
                lobby_list = []
                for trainer in raid_lobby['starting_dict'].keys():
                    user = ctx.guild.get_member(trainer)
                    if not user:
                        continue
                    lobby_list.append(user.mention)
                lobby_str += ", ".join(lobby_list)
                list_embed.add_field(name="**Lobby**", value=lobby_str, inline=False)
                all_lobbies.append(raid_lobby)
            else:
                all_lobbies.append([])
            if raid_active:
                for lobby in raid_active:
                    active_list = []
                    index += 1
                    active_str += f"**{index}.** "
                    for trainer in lobby['starting_dict'].keys():
                        user = ctx.guild.get_member(trainer)
                        if not user:
                            continue
                        active_list.append(user.mention)
                    active_str += ", ".join(active_list)
                    active_str += "\n"
                    all_lobbies.append(lobby)
                list_embed.add_field(name="**Battling**", value=active_str, inline=False)
            if raid_complete:
                for lobby in raid_complete:
                    complete_list = []
                    for trainer in lobby['starting_dict'].keys():
                        user = ctx.guild.get_member(trainer)
                        if not user:
                            continue
                        complete_list.append(user.mention)
                    complete_str += self.bot.custom_emoji.get('bullet', '\U0001F539')
                    complete_str += ", ".join(complete_list)
                    complete_str += "\n"
                list_embed.add_field(name="**Completed**", value=complete_str, inline=False)
            if not raid_lobby and not raid_active and not raid_complete:
                list_embed.description = "Nobody has started this raid."
            if not raid_active and not raid_lobby:
                await ctx.channel.send(embed=list_embed, delete_after=30)
                return
            else:
                await ctx.channel.send("Reply with the number next to a group to tag that group.", embed=list_embed, delete_after=30)
            try:
                lobby_mention = await self.bot.wait_for('message', timeout=30, check=(lambda message: (message.author == ctx.author)))
            except asyncio.TimeoutError:
                return
            if not lobby_mention.content.isdigit():
                return
            await utils.safe_delete(lobby_mention)
            mention_list = []
            for trainer in all_lobbies[int(lobby_mention.content)]['starting_dict'].keys():
                user = ctx.guild.get_member(trainer)
                if not user:
                    continue
                mention_list.append(user.mention)
            await ctx.send(f"Hey {', '.join(mention_list)}! {ctx.author.mention} is trying to get your attention!")


    @_list.command(aliases=['boss'])
    @checks.activeraidchannel()
    async def bosses(self, ctx):
        """List each possible boss and the number of users that have RSVP'd for it.

        Usage: !list bosses
        Works only in raid channels."""
        async with ctx.typing():
            listmsg = _('**Meowth!**')
            listmsg += await self._bosslist(ctx)
            await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _bosslist(self, ctx):
        message = ctx.message
        channel = ctx.channel
        egg_level = self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channel.id]['egg_level']
        egg_level = str(egg_level)
        if egg_level == "0":
            listmsg = _(' The egg has already hatched!')
            return listmsg
        egg_info = self.bot.raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_dict = {}
        boss_list = []
        boss_dict["unspecified"] = {"type": "❔", "total": 0, "maybe": 0, "coming": 0, "here": 0}
        for p in egg_info['pokemon']:
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, p)
            boss_list.append(str(pokemon).lower())
            boss_dict[str(pokemon).lower()] = {"type": "{}".format(pokemon.emoji), "total": 0, "maybe": 0, "coming": 0, "here": 0, "trainers":[]}
        boss_list.append('unspecified')
        trainer_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id]['raidchannel_dict'][channel.id]['trainer_dict'])
        for trainer in trainer_dict:
            user = ctx.guild.get_member(trainer)
            if not user:
                continue
            interest = trainer_dict[trainer].get('interest', ['unspecified'])
            for item in interest:
                status = max(trainer_dict[trainer]['status'], key=lambda key: trainer_dict[trainer]['status'][key])
                count = trainer_dict[trainer]['count']
                boss_dict[item][status] += count
                boss_dict[item]['total'] += count
                boss_dict[item]['trainers'].append(user.display_name)
        bossliststr = ''
        for boss in boss_list:
            if boss_dict[boss]['total'] > 0:
                bossliststr += _('{type} {name}: **{total} total,** {interested} interested, {coming} coming, {here} waiting {type}\n**Trainers:** {trainers}\n\n').format(type=boss_dict[boss]['type'], name=boss.title(), total=boss_dict[boss]['total'], interested=boss_dict[boss]['maybe'], coming=boss_dict[boss]['coming'], here=boss_dict[boss]['here'], trainers=', '.join(boss_dict[boss]['trainers']))
        if bossliststr:
            listmsg = _(' Boss numbers for the raid:\n\n{}').format(bossliststr)
        else:
            listmsg = _(' Nobody has told me what boss they want!')
        return listmsg

    @_list.command(aliases=['team'])
    @checks.rsvpchannel()
    async def teams(self, ctx):
        """List the teams for the users that have RSVP'd to a raid.

        Usage: !list teams
        Works only in raid channels."""
        async with ctx.typing():
            listmsg = _('**Meowth!**')
            listmsg += await self._teamlist(ctx)
            await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))

    async def _teamlist(self, ctx):
        message = ctx.message
        team_dict = {}
        team_dict["mystic"] = {"total":0, "maybe":0, "coming":0, "here":0}
        team_dict["valor"] = {"total":0, "maybe":0, "coming":0, "here":0}
        team_dict["instinct"] = {"total":0, "maybe":0, "coming":0, "here":0}
        team_dict["unknown"] = {"total":0, "maybe":0, "coming":0, "here":0}
        status_list = ["here", "coming", "maybe"]
        team_list = ["mystic", "valor", "instinct", "unknown"]
        teamliststr = ''
        report_dict = await utils.get_report_dict(self.bot, ctx.channel)
        trainer_dict = copy.deepcopy(self.bot.guild_dict[message.guild.id][report_dict][message.channel.id]['trainer_dict'])
        for trainer in trainer_dict.keys():
            if not ctx.guild.get_member(trainer):
                continue
            for team in team_list:
                team_dict[team]["total"] += int(trainer_dict[trainer]['party'][team])
                for status in status_list:
                    if max(trainer_dict[trainer]['status'], key=lambda key: trainer_dict[trainer]['status'][key]) == status:
                        team_dict[team][status] += int(trainer_dict[trainer]['party'][team])
        for team in team_list[:-1]:
            if team_dict[team]['total'] > 0:
                teamliststr += _('{emoji} **{total} total,** {interested} interested, {coming} coming, {here} waiting {emoji}\n').format(emoji=utils.parse_emoji(ctx.guild, self.bot.config.team_dict[team]), total=team_dict[team]['total'], interested=team_dict[team]['maybe'], coming=team_dict[team]['coming'], here=team_dict[team]['here'])
        if team_dict["unknown"]['total'] > 0:
            teamliststr += '{emoji} '.format(emoji=utils.parse_emoji(ctx.guild, self.bot.config.unknown))
            teamliststr += _('**{grey_number} total,** {greymaybe} interested, {greycoming} coming, {greyhere} waiting')
            teamliststr += ' {emoji}'.format(emoji=utils.parse_emoji(ctx.guild, self.bot.config.unknown))
            teamliststr = teamliststr.format(grey_number=team_dict['unknown']['total'], greymaybe=team_dict['unknown']['maybe'], greycoming=team_dict['unknown']['coming'], greyhere=team_dict['unknown']['here'])
        if teamliststr:
            listmsg = _(' Team numbers for the raid:\n\n{}').format(teamliststr)
        else:
            listmsg = _(' Nobody has updated their status!')
        return listmsg

    @_list.command(aliases=['want'])
    @checks.allowwant()
    async def wants(self, ctx):
        """List the wants for the user

        Usage: !list wants
        Works only in the want channel."""
        async with ctx.typing():
            listmsg, res_pages = await self._wantlist(ctx)
            list_messages = []
            if res_pages:
                index = 0
                for p in res_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['want_list'] = {ctx.channel.id: listmsg.id}
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return

    async def _wantlist(self, ctx):
        wantlist = []
        user_link = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        user_mute = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('mute', False)
        mute_mentions = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('mute_mentions', False)
        user_forms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
        user_wants = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_wants = sorted(user_wants)
        wantlist = [utils.get_name(self.bot, x).title() for x in user_wants]
        user_bosses = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_bosses = sorted(user_bosses)
        bosslist = [utils.get_name(self.bot, x).title() for x in user_bosses]
        user_gyms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        user_gyms = [x.title() for x in user_gyms]
        user_stops = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        user_stops = [x.title() for x in user_stops]
        user_items = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        user_items = [x.title() for x in user_items]
        user_types = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        user_types = [x.title() for x in user_types]
        user_ivs = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        user_ivs = sorted(user_ivs)
        user_ivs = [str(x) for x in user_ivs]
        user_levels = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        user_levels = sorted(user_levels)
        user_levels = [str(x) for x in user_levels]
        wantmsg = ""
        if len(wantlist) > 0 or len(user_gyms) > 0 or len(user_stops) > 0 or len(user_items) > 0 or len(bosslist) > 0 or len(user_types) > 0 or len(user_ivs) > 0 or len(user_levels):
            if wantlist:
                wantmsg += _('**Pokemon:** (wilds, research, nests{raid_link})\n{want_list}\n\n').format(want_list='\n'.join(textwrap.wrap(', '.join(wantlist), width=80)), raid_link=", raids" if user_link else "")
            if user_forms:
                wantmsg += _('**Pokemon Forms:** (wilds)\n{want_list}\n\n').format(want_list='\n'.join(textwrap.wrap(', '.join(user_forms), width=80)))
            if bosslist and not user_link:
                wantmsg += _('**Bosses:** (raids)\n{want_list}').format(want_list='\n'.join(textwrap.wrap(', '.join(bosslist), width=80)))
            if user_gyms:
                wantmsg += _('**Gyms:** (raids)\n{user_gyms}\n\n').format(user_gyms='\n'.join(textwrap.wrap(', '.join(user_gyms), width=80)))
            if user_stops:
                wantmsg += _('**Stops:** (research, wilds, lures)\n{user_stops}\n\n').format(user_stops='\n'.join(textwrap.wrap(', '.join(user_stops), width=80)))
            if user_items:
                wantmsg += _('**Items:** (research, lures)\n{user_items}\n\n').format(user_items='\n'.join(textwrap.wrap(', '.join(user_items), width=80)))
            if user_types:
                wantmsg += _('**Types:** (wilds, research, nests)\n{user_types}\n\n').format(user_types='\n'.join(textwrap.wrap(', '.join(user_types), width=80)))
            if user_ivs:
                wantmsg += _('**IVs:** (wilds)\n{user_ivs}\n\n').format(user_ivs='\n'.join(textwrap.wrap(', '.join(user_ivs), width=80)))
            if user_levels:
                wantmsg += _('**Levels:** (wilds)\n{user_levels}\n\n').format(user_levels='\n'.join(textwrap.wrap(', '.join(user_levels), width=80)))
        if wantmsg:
            if user_mute and mute_mentions:
                listmsg = _('Meowth! {author}, your notifications and @mentions are muted, so you will not receive notifications for your current **!want** list:').format(author=ctx.author.display_name)
            elif user_mute and not mute_mentions:
                listmsg = _('Meowth! {author}, your DM notifications are muted, so you will only receive @mention notifications for your current **!want** list:').format(author=ctx.author.display_name)
            elif not user_mute and mute_mentions:
                listmsg = _('Meowth! {author}, your @mentions are muted, so you will only receive DM notifications for your current **!want** list:').format(author=ctx.author.display_name)
            else:
                listmsg = _('Meowth! {author}, you will receive notifications for your current **!want** list:').format(author=ctx.author.display_name)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wantmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! {author}, you don\'t have any wants! use **!want** to add some.").format(author=ctx.author.display_name)
        return listmsg, None

    @_list.command()
    @commands.has_permissions(manage_guild=True)
    @checks.allowwant()
    async def allwants(self, ctx):
        """List the wants for the server

        Usage: !list wants
        Works only in the want channel."""
        async with ctx.typing():
            listmsg, res_pages = await self._allwantlist(ctx)
            list_messages = []
            if res_pages:
                index = 0
                for p in res_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return

    async def _allwantlist(self, ctx):
        want_list = []
        form_list = []
        stop_list = []
        gym_list = []
        boss_list = []
        item_list = []
        type_list = []
        iv_list = []
        level_list = []
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('wants', []):
                if want not in want_list:
                    want_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('forms', []):
                if want not in form_list:
                    form_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('stops', []):
                if want not in stop_list:
                    stop_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('gyms', []):
                if want not in gym_list:
                    gym_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('bosses', []):
                if want not in boss_list:
                    boss_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('items', []):
                if want not in item_list:
                    item_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('types', []):
                if want not in type_list:
                    type_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('ivs', []):
                if want not in iv_list:
                    iv_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('levels', []):
                if want not in level_list:
                    level_list.append(want)
        want_list = sorted(want_list)
        want_list = [utils.get_name(self.bot, x).title() for x in want_list]
        stop_list = [x.title() for x in stop_list]
        gym_list = [x.title() for x in gym_list]
        boss_list = sorted(boss_list)
        boss_list = [utils.get_name(self.bot, x).title() for x in boss_list]
        item_list = [x.title() for x in item_list]
        type_list = [x.title() for x in type_list]
        iv_list = sorted(iv_list)
        iv_list = [str(x) for x in iv_list]
        level_list = sorted(level_list)
        level_list = [str(x) for x in level_list]
        wantmsg = ""
        if len(want_list) > 0 or len(gym_list) > 0 or len(stop_list) > 0 or len(item_list) > 0 or len(boss_list) > 0 or len(type_list) > 0 or len(iv_list) > 0 or len(level_list):
            if want_list:
                wantmsg += _('**Pokemon:**\n{want_list}\n\n').format(want_list='\n'.join(textwrap.wrap(', '.join(want_list), width=80)))
            if want_list:
                wantmsg += _('**Pokemon Forms:**\n{want_list}\n\n').format(want_list='\n'.join(textwrap.wrap(', '.join(form_list), width=80)))
            if boss_list:
                wantmsg += _('**Bosses:**\n{want_list}\n\n').format(want_list='\n'.join(textwrap.wrap(', '.join(boss_list), width=80)))
            if gym_list:
                wantmsg += _('**Gyms:**\n{user_gyms}\n\n').format(user_gyms='\n'.join(textwrap.wrap(', '.join(gym_list), width=80)))
            if stop_list:
                wantmsg += _('**Stops:**\n{user_stops}\n\n').format(user_stops='\n'.join(textwrap.wrap(', '.join(stop_list), width=80)))
            if item_list:
                wantmsg += _('**Items:**\n{user_items}\n\n').format(user_items='\n'.join(textwrap.wrap(', '.join(item_list), width=80)))
            if type_list:
                wantmsg += _('**Types:**\n{user_types}\n\n').format(user_types='\n'.join(textwrap.wrap(', '.join(type_list), width=80)))
            if iv_list:
                wantmsg += _('**IVs:**\n{user_ivs}\n\n').format(user_ivs='\n'.join(textwrap.wrap(', '.join(iv_list), width=80)))
            if level_list:
                wantmsg += _('**Levels:**\n{user_levels}\n\n').format(user_levels='\n'.join(textwrap.wrap(', '.join(level_list), width=80)))
        if wantmsg:
            listmsg = _('**Meowth!** The server **!want** list is:')
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wantmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("**Meowth!** Nobody has any wants! use **!want** to add some.")
        return listmsg, None

    @_list.command(aliases=['trade'])
    @checks.allowtrade()
    async def trades(self, ctx, *, search=None):
        """List the trades for the user or pokemon

        Usage: !list trades [user or pokemon]
        Works only in trading channels."""
        async with ctx.typing():
            if not search:
                search = ctx.author
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
                if pokemon:
                    search = str(pokemon)
                elif "shiny" in search.lower():
                    search = "shiny"
                else:
                    converter = commands.MemberConverter()
                    try:
                        search = await converter.convert(ctx, search)
                    except Exception as e:
                        search = ctx.author
            listmsg, res_pages = await self._tradelist(ctx, search)
            list_messages = []
            if res_pages:
                index = 0
                for p in res_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                        if search == ctx.author:
                            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trade_list'] = {ctx.channel.id: listmsg.id}
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return

    async def _tradelist(self, ctx, search):
        tgt_trainer_trades = {}
        tgt_pokemon_trades = {}
        tgt_shiny_trades = {}
        target_trades = {}
        listmsg = ""
        trademsg = ""
        lister_str = ""
        for offer_id in self.bot.guild_dict[ctx.guild.id]['trade_dict']:
            if self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['report_channel_id'] != ctx.channel.id:
                continue
            if isinstance(search, discord.member.Member):
                if self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['lister_id'] == search.id:
                    tgt_trainer_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
            elif search == "shiny":
                if "shiny" in self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['offered_pokemon'].lower():
                    tgt_shiny_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
                if str(pokemon) in self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['offered_pokemon']:
                    tgt_pokemon_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
        if tgt_trainer_trades:
            listmsg = _("Meowth! Here are the current trades for {user}.").format(user=search.display_name)
        elif tgt_pokemon_trades:
            listmsg = _("Meowth! Here are the current {pokemon} trades.").format(pokemon=str(pokemon))
        elif tgt_shiny_trades:
            listmsg = _("Meowth! Here are the current Shiny trades.")
        target_trades = {**tgt_trainer_trades, **tgt_shiny_trades, **tgt_pokemon_trades}
        if target_trades:
            for offer_id in target_trades:
                offer_url = ""
                try:
                    offer_channel = self.bot.get_channel(
                        target_trades[offer_id]['report_channel_id'])
                    offer_message = await offer_channel.fetch_message(offer_id)
                    offer_url = offer_message.jump_url
                except:
                    continue
                lister = ctx.guild.get_member(target_trades[offer_id]['lister_id'])
                if not lister:
                    continue
                if tgt_pokemon_trades:
                    lister_str = f"**Lister**: {lister.display_name} | "
                wanted_pokemon = target_trades[offer_id]['wanted_pokemon']
                if "Open Trade" in wanted_pokemon:
                    wanted_pokemon = "Open Trade (DM User)"
                else:
                    wanted_pokemon = [await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, x) for x in wanted_pokemon.split('\n')]
                    wanted_pokemon = [str(x) for x in wanted_pokemon]
                    wanted_pokemon = ', '.join(wanted_pokemon)
                trademsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('trade_bullet', '\U0001F539')))
                trademsg += (f"{lister_str}**Offered Pokemon**: {target_trades[offer_id]['offered_pokemon']} | **Wanted Pokemon**: {wanted_pokemon} | [Jump To Message]({offer_url})")
        if trademsg:
            paginator = commands.Paginator(prefix="", suffix="")
            for line in trademsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! No active trades found. List one with **!trade**")
        return listmsg, None

    @_list.command()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowresearchreport()
    async def research(self, ctx):
        """List the quests for the channel

        Usage: !list research"""
        await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('research', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            listmsg, res_pages = await self._researchlist(ctx)
            list_messages = []
            if res_pages:
                index = 0
                for p in res_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return
            self.bot.guild_dict[ctx.guild.id]['list_dict']['research'][ctx.channel.id] = list_messages

    async def _researchlist(self, ctx):
        research_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('questreport_dict', {}))
        quest_dict = {'encounters':{}, 'candy':{}, 'dust':{}, 'berry':{}, 'potion':{}, 'revive':{}, 'ball':{}, 'other':{}}
        reward_dict = {'encounters':[], 'candy':[], 'dust':[], 'berry':[], 'potion':[], 'revive':[], 'ball':[], 'other':[]}
        questmsg = ""
        item_quests = []
        encounter_quests = []
        dust_quests = []
        dust_dict = {}
        candy_quests = []
        berry_quests = []
        potion_quests = []
        revive_quests = []
        ball_quests = []
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy"]
        encounter_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_encounter', '\u2753'))
        candy_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_candy', '\U0001F36C'))
        dust_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_dust', '\u2b50'))
        berry_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_berry', '\U0001F353'))
        potion_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_potion', '\U0001F48A'))
        revive_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_revive', '\u2764'))
        ball_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_ball', '\u26be'))
        other_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_other', '\U0001F539'))
        for questid in research_dict:
            pokemon = None
            if research_dict[questid]['report_channel'] == ctx.message.channel.id:
                try:
                    questreportmsg = await ctx.message.channel.fetch_message(questid)
                    questauthor = ctx.channel.guild.get_member(research_dict[questid]['report_author'])
                    reported_by = ""
                    if questauthor and not questauthor.bot:
                        reported_by = f" | **Reported By**: {questauthor.display_name}"
                    quest = research_dict[questid]['quest']
                    reward = research_dict[questid]['reward']
                    location = research_dict[questid]['location']
                    url = research_dict[questid].get('url', None)
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward, allow_digits = False)
                    other_reward = any(x in reward for x in reward_list)
                    if pokemon and not other_reward:
                        shiny_str = ""
                        if pokemon.id in self.bot.shiny_dict:
                            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "research" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                        quest_dict['encounters'][questid] = {"reward":f"{shiny_str}{reward} {pokemon.emoji}", "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "pokemon":pokemon.name}
                        if pokemon.name not in reward_dict['encounters']:
                            reward_dict['encounters'].append(pokemon.name)
                    elif "candy" in reward.lower() or "candies" in reward.lower():
                        quest_dict['candy'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['candy']:
                            reward_dict['candy'].append(reward)
                    elif "dust" in reward.lower():
                        quest_dict['dust'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['dust']:
                            reward_dict['dust'].append(reward)
                    elif "berry" in reward.lower() or "berries" in reward.lower() or "razz" in reward.lower() or "pinap" in reward.lower() or "nanab" in reward.lower():
                        quest_dict['berry'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['berry']:
                            reward_dict['berry'].append(reward)
                    elif "potion" in reward.lower():
                        quest_dict['potion'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['potion']:
                            reward_dict['potion'].append(reward)
                    elif "revive" in reward.lower():
                        quest_dict['revive'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['revive']:
                            reward_dict['revive'].append(reward)
                    elif "ball" in reward.lower():
                        quest_dict['ball'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['ball']:
                            reward_dict['ball'].append(reward)
                    else:
                        quest_dict['other'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url}
                        if reward not in reward_dict['other']:
                            reward_dict['other'].append(reward)
                except:
                    continue
        for pkmn in sorted(reward_dict['encounters']):
            for quest in quest_dict['encounters']:
                if quest_dict['encounters'][quest]['pokemon'] == pkmn and not quest_dict['encounters'][quest].get('listed', False):
                    encounter_quests.append(f"{encounter_emoji} **Reward**: {quest_dict['encounters'][quest]['reward']} | **Pokestop**: {quest_dict['encounters'][quest]['location']} | **Quest**: {quest_dict['encounters'][quest]['quest']}{quest_dict['encounters'][quest]['reporter']}")
                    quest_dict['encounters'][quest]['listed'] = True
        if encounter_quests:
            questmsg += "\n\n**Pokemon Encounters**\n{encounterlist}".format(encounterlist="\n".join(encounter_quests))
        for candy in sorted(reward_dict['candy']):
            for quest in quest_dict['candy']:
                if quest_dict['candy'][quest]['reward'] == candy and not quest_dict['candy'][quest].get('listed', False):
                    candy_quests.append(f"{candy_emoji} **Reward**: {quest_dict['candy'][quest]['reward']} | **Pokestop**: {quest_dict['candy'][quest]['location']} | **Quest**: {quest_dict['candy'][quest]['quest']}{quest_dict['candy'][quest]['reporter']}")
                    quest_dict['candy'][quest]['listed'] = True
        if candy_quests:
            questmsg += "\n\n**Rare Candy**\n{candylist}".format(candylist="\n".join(candy_quests))
        for berry in sorted(reward_dict['berry']):
            for quest in quest_dict['berry']:
                if quest_dict['berry'][quest]['reward'] == berry and not quest_dict['berry'][quest].get('listed', False):
                    berry_quests.append(f"{berry_emoji} **Reward**: {quest_dict['berry'][quest]['reward']} | **Pokestop**: {quest_dict['berry'][quest]['location']} | **Quest**: {quest_dict['berry'][quest]['quest']}{quest_dict['berry'][quest]['reporter']}")
                    quest_dict['berry'][quest]['listed'] = True
        if berry_quests:
            questmsg += "\n\n**Berries**\n{itemlist}".format(itemlist="\n".join(berry_quests))
        for potion in sorted(reward_dict['potion']):
            for quest in quest_dict['potion']:
                if quest_dict['potion'][quest]['reward'] == potion and not quest_dict['potion'][quest].get('listed', False):
                    potion_quests.append(f"{potion_emoji} **Reward**: {quest_dict['potion'][quest]['reward']} | **Pokestop**: {quest_dict['potion'][quest]['location']} | **Quest**: {quest_dict['potion'][quest]['quest']}{quest_dict['potion'][quest]['reporter']}")
                    quest_dict['potion'][quest]['listed'] = True
        if potion_quests:
            questmsg += "\n\n**Potions**\n{itemlist}".format(itemlist="\n".join(potion_quests))
        for revive in sorted(reward_dict['revive']):
            for quest in quest_dict['revive']:
                if quest_dict['revive'][quest]['reward'] == revive and not quest_dict['revive'][quest].get('listed', False):
                    revive_quests.append(f"{revive_emoji} **Reward**: {quest_dict['revive'][quest]['reward']} | **Pokestop**: {quest_dict['revive'][quest]['location']} | **Quest**: {quest_dict['revive'][quest]['quest']}{quest_dict['revive'][quest]['reporter']}")
                    quest_dict['revive'][quest]['listed'] = True
        if revive_quests:
            questmsg += "\n\n**Revives**\n{itemlist}".format(itemlist="\n".join(revive_quests))
        for ball in sorted(reward_dict['ball']):
            for quest in quest_dict['ball']:
                if quest_dict['ball'][quest]['reward'] == ball and not quest_dict['ball'][quest].get('listed', False):
                    ball_quests.append(f"{ball_emoji} **Reward**: {quest_dict['ball'][quest]['reward']} | **Pokestop**: {quest_dict['ball'][quest]['location']} | **Quest**: {quest_dict['ball'][quest]['quest']}{quest_dict['ball'][quest]['reporter']}")
                    quest_dict['ball'][quest]['listed'] = True
        if ball_quests:
            questmsg += "\n\n**Poke Balls**\n{itemlist}".format(itemlist="\n".join(ball_quests))
        for item in sorted(reward_dict['other']):
            for quest in quest_dict['other']:
                if quest_dict['other'][quest]['reward'] == item and not quest_dict['other'][quest].get('listed', False):
                    item_quests.append(f"{other_emoji} **Reward**: {quest_dict['other'][quest]['reward']} | **Pokestop**: {quest_dict['other'][quest]['location']} | **Quest**: {quest_dict['other'][quest]['quest']}{quest_dict['other'][quest]['reporter']}")
                    quest_dict['other'][quest]['listed'] = True
        if item_quests:
            questmsg += "\n\n**Other Rewards**\n{itemlist}".format(itemlist="\n".join(item_quests))
        for dust in sorted(reward_dict['dust']):
            for quest in dust_dict:
                if dust_dict[quest]['reward'] == dust and not dust_dict[quest].get('listed', False):
                    dust_quests.append(f"{dust_emoji} **Reward**: {dust_dict[quest]['reward']} | **Pokestop**: {dust_dict[quest]['location']} | **Quest**: {dust_dict[quest]['quest']}{dust_dict[quest]['reporter']}")
                    dust_dict[quest]['listed'] = True
        if dust_quests:
            questmsg += "\n\n**Stardust**\n{dustlist}".format(dustlist="\n".join(dust_quests))
        if questmsg:
            listmsg = _('**Meowth! Here\'s the current research reports for {channel}**').format(channel=ctx.message.channel.mention)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in questmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! There are no reported research reports. Report one with **!research**")
        return listmsg, None

    @_list.command()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowlurereport()
    async def lures(self, ctx):
        """List the lures for the channel

        Usage: !list lures"""
        await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('lure', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            listmsg, lure_pages = await self._lurelist(ctx)
            list_messages = []
            if lure_pages:
                index = 0
                for p in lure_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return
            self.bot.guild_dict[ctx.guild.id]['list_dict']['lure'][ctx.channel.id] = list_messages

    async def _lurelist(self, ctx):
        lure_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('lure_dict', {}))
        luremsg = ""
        for lureid in lure_dict:
            if lure_dict[lureid]['report_channel'] == ctx.message.channel.id:
                try:
                    lurereportmsg = await ctx.message.channel.fetch_message(lureid)
                    lureauthor = ctx.channel.guild.get_member(lure_dict[lureid]['report_author'])
                    lure_expire = datetime.datetime.utcfromtimestamp(lure_dict[lureid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
                    reported_by = ""
                    if lureauthor and not lureauthor.bot:
                        reported_by = f" | **Reported By**: {lureauthor.display_name}"
                    iv_check = lure_dict[lureid].get('lure_iv', None)
                    luremsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('lure_bullet', '\U0001F539')))
                    luremsg += f"**Lure Type**: {lure_dict[lureid]['type'].title()} | **Location**: [{lure_dict[lureid]['location'].title()}]({lure_dict[lureid].get('url', None)}) | **Expires**: {lure_expire.strftime(_('%I:%M %p'))}{reported_by}"
                except Exception as e:
                    print(e)
                    continue
        if luremsg:
            listmsg = _('**Meowth! Here\'s the current lure reports for {channel}**').format(channel=ctx.message.channel.mention)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in luremsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! There are no reported lures. Report one with **!lure**")
        return listmsg, None

    @_list.command()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowpvpreport()
    async def pvp(self, ctx):
        """List the pvps for the channel

        Usage: !list pvps"""
        await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('pvp', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            listmsg, pvp_pages = await self._pvplist(ctx)
            list_messages = []
            if pvp_pages:
                index = 0
                for p in pvp_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return
            self.bot.guild_dict[ctx.guild.id]['list_dict']['pvp'][ctx.channel.id] = list_messages

    async def _pvplist(self, ctx):
        pvp_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('pvp_dict', {}))
        pvpmsg = ""
        for pvpid in pvp_dict:
            if pvp_dict[pvpid]['report_channel'] == ctx.message.channel.id:
                try:
                    pvpreportmsg = await ctx.message.channel.fetch_message(pvpid)
                    pvpauthor = ctx.channel.guild.get_member(pvp_dict[pvpid]['report_author'])
                    pvp_tournament = pvp_dict[pvpid].get('tournament', {})
                    pvp_expire = datetime.datetime.utcfromtimestamp(pvp_dict[pvpid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
                    reported_by = ""
                    if pvpauthor and not pvpauthor.bot:
                        reported_by = f" | **Requested By**: {pvpauthor.display_name}"
                    pvpmsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('pvp_bullet', '\U0001F539')))
                    if pvp_tournament:
                        pvpmsg += f"**PVP Type**: {pvp_dict[pvpid]['type'].title()} Tournament | **Location**: [{pvp_dict[pvpid]['location'].title()}]({pvp_dict[pvpid].get('url', None)}) | **Tournament Size**: {pvp_tournament['size']} | **Round**: {pvp_tournament['round']}{reported_by}"
                        pass
                    else:
                        pvpmsg += f"**PVP Type**: {pvp_dict[pvpid]['type'].title()} | **Location**: [{pvp_dict[pvpid]['location'].title()}]({pvp_dict[pvpid].get('url', None)}) | **Available Until**: {pvp_expire.strftime(_('%I:%M %p'))}{reported_by}"
                except Exception as e:
                    print(e)
                    continue
        if pvpmsg:
            listmsg = _('**Meowth! Here\'s the current PVP Requests for {channel}**').format(channel=ctx.message.channel.mention)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in pvpmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! There are no requested PVP battles. Report one with **!pvp**")
        return listmsg, None

    @_list.command(aliases=['wild'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowwildreport()
    async def wilds(self, ctx):
        """List the wilds for the channel

        Usage: !list wilds"""
        await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('wild', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            listmsg, wild_pages = await self._wildlist(ctx)
            list_messages = []
            if wild_pages:
                index = 0
                for p in wild_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return
            self.bot.guild_dict[ctx.guild.id]['list_dict']['wild'][ctx.channel.id] = list_messages

    async def _wildlist(self, ctx):
        wild_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('wildreport_dict', {}))
        wildmsg = ""
        for wildid in wild_dict:
            if wild_dict[wildid]['report_channel'] == ctx.message.channel.id:
                try:
                    wildreportmsg = await ctx.message.channel.fetch_message(wildid)
                    wildauthor = ctx.channel.guild.get_member(wild_dict[wildid]['report_author'])
                    wild_despawn = datetime.datetime.utcfromtimestamp(wild_dict[wildid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
                    reported_by = ""
                    if wildauthor and not wildauthor.bot:
                        reported_by = f" | **Reported By**: {wildauthor.display_name}"
                    shiny_str = ""
                    iv_check = wild_dict[wildid].get('wild_iv', {})
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, wild_dict[wildid]['pkmn_obj'])
                    if pokemon.id in self.bot.shiny_dict:
                        if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                        elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                    wildmsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('wild_bullet', '\U0001F539')))
                    wildmsg += f"**Pokemon**: {shiny_str}{pokemon.name.title()} {pokemon.emoji} | **Location**: [{wild_dict[wildid]['location'].title()}]({wild_dict[wildid].get('url', None)}) | **Despawns**: {wild_despawn.strftime(_('%I:%M %p'))}{reported_by}"
                    if iv_check:
                        wildmsg += f", **IV**: {wild_dict[wildid]['wild_iv'].get('percent', iv_check)}"
                except Exception as e:
                    print(e)
                    continue
        if wildmsg:
            listmsg = _('**Meowth! Here\'s the current wild reports for {channel}**').format(channel=ctx.message.channel.mention)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wildmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! There are no reported wild pokemon. Report one with **!wild <pokemon> <location>**")
        return listmsg, None

    @_list.command(aliases=['nest'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allownestreport()
    async def nests(self, ctx):
        """List the nests for the channel

        Usage: !list nests"""
        await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('nest', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            nest_cog = self.bot.cogs.get('Nest')
            if not nest_cog:
                return
            list_messages = []
            nest_embed, nest_pages = await nest_cog.get_nest_reports(ctx)
            index = 0
            for p in nest_pages:
                nest_embed.description = p
                if index == 0:
                    listmsg = await ctx.channel.send(_('**Meowth!** Here\'s the current nests for {channel}').format(channel=ctx.channel.mention), embed=nest_embed)
                else:
                    listmsg = await ctx.channel.send(embed=nest_embed)
                list_messages.append(listmsg.id)
                index += 1
            self.bot.guild_dict[ctx.guild.id]['list_dict']['nest'][ctx.channel.id] = list_messages

def setup(bot):
    bot.add_cog(Listing(bot))

def teardown(bot):
    bot.remove_cog(Listing)

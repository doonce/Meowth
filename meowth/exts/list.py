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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        if guild and guild.id not in list(self.bot.guild_dict.keys()):
            return
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        else:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        can_manage = channel.permissions_for(user).manage_messages
        list_dict = self.bot.guild_dict[guild.id].setdefault('list_dict', {})
        for list_type in list_dict:
            if channel.id not in list_dict[list_type]:
                continue
            for list_channel in list_dict[list_type]:
                if message.id in list_dict[list_type][list_channel]:
                    ctx.author, ctx.message.author = user, user
                    await utils.remove_reaction(message, payload.emoji, user)
                    if list_type == "wild" and str(payload.emoji) == self.bot.custom_emoji.get('wild_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('wild'))
                    elif list_type == "raid" and str(payload.emoji) == self.bot.custom_emoji.get('raid_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('raid'))
                    elif list_type == "pvp" and str(payload.emoji) == self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('pvp'))
                    elif list_type == "lure" and str(payload.emoji) == self.bot.custom_emoji.get('lure_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('lure'))
                    elif list_type == "invasion" and str(payload.emoji) == self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('invasion'))
                    elif list_type == "research" and str(payload.emoji) == self.bot.custom_emoji.get('research_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('research'))
                    elif list_type == "nest" and str(payload.emoji) == self.bot.custom_emoji.get('nest_report', u'\U0001F4E2'):
                        return await ctx.invoke(self.bot.get_command('nest'))

    @commands.group(name="list", aliases=['lists', 'tag', 'l'], invoke_without_command=True, case_insensitive=True)
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def _list(self, ctx, *, search_term="all"):
        """Lists all info for the current reports depending on channel type.

        Usage: !list
        Works only in raid or reporting channels. In raid channels this calls the interested, waiting, and here list and prints
        the raid timer. In reporting channels, this lists all active reports.

        Raid Reporting Channel Listing Options: pokemon, location, type"""
        if not ctx.guild:
            ctx.invoked_with = "dm"
            return await ctx.invoke(self.bot.get_command('list dm'))
        if str(ctx.invoked_with).lower() in ['list', 'lists', 'tag', 'l']:
            await utils.safe_delete(ctx.message)
        if ctx.invoked_subcommand == None:
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            async with ctx.typing():
                listmsg = _('**Meowth!** ')
                temp_list = ""
                raid_list = ""
                guild = ctx.guild
                channel = ctx.channel
                now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                list_messages = []
                raid_cog = self.bot.cogs.get('Raid')
                report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
                if (checks.check_raidreport(ctx) or checks.check_exraidreport(ctx) or checks.check_meetupreport(ctx)):
                    if not raid_cog:
                        return
                    if str(ctx.invoked_with).lower() == "tag":
                        tag_error = await channel.send(f"Please use **{ctx.prefix}{ctx.invoked_with}** in an active raid channel.", delete_after=10)
                        await asyncio.sleep(10)
                        await utils.safe_delete(ctx.message)
                        await utils.safe_delete(tag_error)
                        return
                    raid_list, search_label = await self._raidlist(ctx, search_term)
                    list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
                    if not raid_list:
                        if "all" not in ctx.message.content.lower():
                            ctx.message.content = "!list all"
                            return await ctx.invoke(self.bot.get_command("list"))
                        list_embed.add_field(name=f"**No Current Channel Reports**", value=f"Meowth! There are no active {search_label}. Report a raid with **{ctx.prefix}raid <name> <location> [weather] [timer]** or react with {report_emoji} and I can walk you through it!")
                        list_message = await ctx.channel.send(embed=list_embed)
                        await utils.add_reaction(list_message, report_emoji)
                        list_messages.append(list_message.id)
                    else:
                        listmsg += f"**Here are the {'active' if 'all' not in ctx.message.content.lower() else 'current'} {search_label} for {channel.mention}**.{' You can use **'+ctx.prefix+'list all** to see all channels!' if 'all' not in ctx.message.content.lower() else ''}\n\n"
                        raid_list += f"**New Report:**\nReact with {report_emoji} to start a new raid, train, or meetup report!"
                        paginator = commands.Paginator(prefix="", suffix="")
                        index = 0
                        for line in raid_list.splitlines():
                            paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                        for p in paginator.pages:
                            list_embed.description = p
                            if index == 0:
                                list_message = await ctx.send(listmsg, embed=list_embed)
                            else:
                                list_message = await ctx.send(embed=list_embed)
                            list_messages.append(list_message.id)
                            index += 1
                        await utils.add_reaction(list_message, report_emoji)
                    self.bot.guild_dict[ctx.guild.id]['list_dict']['raid'][ctx.channel.id] = list_messages
                    for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['raid']):
                        if not ctx.guild.get_channel(channel):
                            del self.bot.guild_dict[ctx.guild.id]['list_dict']['raid'][channel]

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
                        bulletpoint = self.bot.custom_emoji.get('bullet', u'\U0001F539')
                    if " 0 interested!" not in await self._interest(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._interest(ctx, tag, team))
                    if " 0 on the way!" not in await self._otw(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._otw(ctx, tag, team))
                    if " 0 waiting at the" not in await self._waiting(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._waiting(ctx, tag, team))
                    if " 0 in the lobby!" not in await self._lobbylist(ctx, tag, team):
                        listmsg += ('\n' + bulletpoint) + (await self._lobbylist(ctx, tag, team))
                    if (len(listmsg.splitlines()) <= 1):
                        listmsg +=  ('\n' + bulletpoint) + (_(" Nobody has updated their status yet!"))
                    listmsg += ('\n' + bulletpoint) + (await raid_cog.print_raid_timer(channel))
                    if starttime and (starttime > now) and not meetup:
                        listmsg += _('\nThe next group will be starting at **{}**').format(starttime.strftime(_('%I:%M %p (%H:%M)')))
                    if checks.check_trainchannel(ctx):
                        manager_list = [ctx.guild.get_member(x) for x in self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id]['managers']]
                        listmsg += f"\n{bulletpoint} Managers: {(', ').join(['**'+x.display_name+'**' for x in manager_list]) if not tag else (', ').join([x.mention for x in manager_list])}"
                    if raid_message:
                        list_embed = discord.Embed(colour=ctx.guild.me.colour, description=listmsg, title=raid_message.embeds[0].title, url=raid_message.embeds[0].url)
                        if len(raid_message.embeds[0].fields) > 4:
                            for field in raid_message.embeds[0].fields:
                                if "status" in field.name.lower() or "team" in field.name.lower():
                                    list_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                    else:
                        list_embed = discord.Embed(colour=ctx.guild.me.colour, description=listmsg)
                    list_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
                    if tag:
                        list_msg = await ctx.channel.send(listmsg)
                    else:
                        list_msg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(list_msg.id)
                    self.bot.guild_dict[guild.id].setdefault('list_dict', {}).setdefault('raid', {})[channel.id] = list_messages
                    for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['raid']):
                        if not ctx.guild.get_channel(channel):
                            del self.bot.guild_dict[ctx.guild.id]['list_dict']['raid'][channel]
                    return
                else:
                    channel_check = sum(bool(x) for x in [checks.check_wantchannel(ctx), checks.check_wildreport(ctx), checks.check_nestreport(ctx), checks.check_researchreport(ctx), checks.check_tradereport(ctx), checks.check_lurereport(ctx), checks.check_pvpreport(ctx), checks.check_invasionreport(ctx)])
                    if channel_check == 1:
                        if checks.check_wantchannel(ctx):
                            return await ctx.invoke(self.bot.get_command('list wants'))
                        elif checks.check_wildreport(ctx):
                            return await ctx.invoke(self.bot.get_command('list wild'), search_term=search_term)
                        elif checks.check_researchreport(ctx):
                            return await ctx.invoke(self.bot.get_command('list research'), search_term=search_term)
                        elif checks.check_nestreport(ctx):
                            return await ctx.invoke(self.bot.get_command('list nest'))
                        elif checks.check_tradereport(ctx):
                            return await ctx.invoke(self.bot.get_command('list trades'), search=search_term)
                        elif checks.check_lurereport(ctx):
                            return await ctx.invoke(self.bot.get_command('list lures'), search_term=search_term)
                        elif checks.check_pvpreport(ctx):
                            return await ctx.invoke(self.bot.get_command('list pvp'), search_term=search_term)
                        elif checks.check_invasionreport(ctx):
                            return await ctx.invoke(self.bot.get_command('list invasions'), search_term=search_term)
                    elif channel_check > 1:
                        list_types = ['list wants' if checks.check_wantchannel(ctx) else False, 'list wilds' if checks.check_wildreport(ctx) else False, 'list nest' if checks.check_nestreport(ctx) else False, 'list research' if checks.check_researchreport(ctx) else False, 'list trades' if checks.check_tradereport(ctx) else False, 'list lures' if checks.check_lurereport(ctx) else False, 'list pvp' if checks.check_pvpreport(ctx) else False, 'list invasions' if checks.check_invasionreport(ctx) else False]
                        list_types = [f"{ctx.prefix}{x}" for x in list_types if x]
                        await ctx.send(f"**Meowth!** I don't know what list you wanted. Try **{', '.join(list_types)}**", delete_after=10)
                    else:
                        raise checks.errors.CityRaidChannelCheckFail()

    async def _raidlist(self, ctx, search_term="all"):
        raid_cog = self.bot.cogs.get('Raid')
        listmsg = _('**Meowth!** ')
        temp_list = ""
        raid_list = ""
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        list_messages = []
        search_label = "channels"
        if "all" in ctx.message.content.lower():
            search_term = "all"
        elif search_term != "all":
            search_term = search_term.lower()
            pois = {}
            search_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search_term)
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            if gym_matching_cog:
                pois = {**gym_matching_cog.get_gyms(ctx.guild.id)}
                pois = {k.lower(): v for k, v in pois.items()}
            if search_term in self.bot.type_list:
                search_label = f"{search_term.title()} type channels"
            elif search_term.lower() in [x.lower() for x in pois.keys()]:
                if pois[search_term].get('alias'):
                    search_term = pois[search_term].get('alias')
                search_label = f"channels at {search_term.title()}"
            elif search_pokemon:
                search_term = search_pokemon.name.lower()
                search_label = f"{search_term.title()} channels"
        else:
            search_term = None
        rc_d = {**self.bot.guild_dict[ctx.guild.id]['raidchannel_dict'], **self.bot.guild_dict[ctx.guild.id]['exraidchannel_dict'], **self.bot.guild_dict[ctx.guild.id]['meetup_dict'], **self.bot.guild_dict[ctx.guild.id]['raidtrain_dict']}
        raid_dict = {}
        egg_dict = {}
        exraid_list = []
        event_list = []
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('raid', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        for msg in list_dict:
            try:
                msg = await ctx.channel.fetch_message(msg)
                delete_list.append(msg)
            except:
                pass
        await utils.safe_bulk_delete(ctx.channel, delete_list)
        mystic_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['mystic'])
        valor_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['valor'])
        instinct_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['instinct'])
        unknown_emoji = utils.parse_emoji(ctx.guild, self.bot.config.unknown)
        for r in rc_d:
            report_channel = self.bot.get_channel(rc_d[r]['report_channel'])
            if not report_channel:
                continue
            condition_check = report_channel.id == ctx.channel.id
            if "dm" in str(ctx.invoked_with):
                ctx.message.content = "all"
                condition_check = ctx.author.id in rc_d[r].get('dm_dict', {})
            if condition_check:
                exp = rc_d[r]['exp']
                type = rc_d[r]['type']
                level = rc_d[r]['egg_level']
                if (type == 'egg') and level.isdigit():
                    egg_dict[r] = exp
                elif rc_d[r].get('meetup', {}) and rc_d[r]['active']:
                    event_list.append(r)
                elif ((type == 'exraid') or (level == 'EX')) and rc_d[r]['active'] :
                    exraid_list.append(r)
                elif rc_d[r]['active'] :
                    raid_dict[r] = exp

        async def list_output(r):
            trainer_dict = rc_d[r]['trainer_dict']
            location = rc_d[r]['address']
            rchan = self.bot.get_channel(r)
            end = datetime.datetime.utcfromtimestamp(rc_d[r]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
            output = ''
            start_str = ''
            channel_dict, boss_dict = await raid_cog._get_party(rchan)
            if not channel_dict['total'] and "all" not in ctx.message.content.lower() and not search_term:
                return None
            if rc_d[r]['manual_timer'] == False:
                assumed_str = _(' (assumed)')
            else:
                assumed_str = ''
            if channel_dict.get('train', False):
                train_str = "{train_emoji} - ".format(train_emoji=self.bot.custom_emoji.get('train_emoji', u'\U0001F682'))
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
                if self.bot.active_channels.get(r, {}).get('pokemon'):
                    pokemon = self.bot.active_channels[r]['pokemon']
                else:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, rc_d[r].get('pkmn_obj', ""))
            elif ((rc_d[r]['egg_level'] == 'EX') or (rc_d[r]['type'] == 'exraid')) and not meetup:
                expirytext = _(' - {train_str}Hatches: {expiry}{is_assumed}').format(train_str=train_str, expiry=end.strftime(_('%B %d at %I:%M %p (%H:%M)')), is_assumed=assumed_str)
                if self.bot.active_channels.get(r, {}).get('pokemon'):
                    pokemon = self.bot.active_channels[r]['pokemon']
                else:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, rc_d[r].get('pkmn_obj', ""))
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
                if self.bot.active_channels.get(r, {}).get('pokemon'):
                    pokemon = self.bot.active_channels[r]['pokemon']
                else:
                    pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, rc_d[r].get('pkmn_obj', ""))
                if pokemon:
                    type_str = pokemon.emoji
                expirytext = _('{type_str} - {train_str}Expires: {expiry}{is_assumed}').format(type_str=type_str, train_str=train_str, expiry=end.strftime(_('%I:%M %p (%H:%M)')), is_assumed=assumed_str)

            if search_term and search_term != "all":
                if str(getattr(pokemon, 'name', None)).lower() == search_term:
                    pass
                elif search_term.title() in pokemon.types:
                    pass
                elif search_term.lower() == location.lower():
                    pass
                else:
                    return None

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
                output += f" | {mystic_emoji}: **{channel_dict['mystic']}**"
            if channel_dict['valor']:
                output += f" | {valor_emoji}: **{channel_dict['valor']}**"
            if channel_dict['instinct']:
                output += f" | {instinct_emoji}: **{channel_dict['instinct']}**"
            if channel_dict['unknown']:
                output += f" | {unknown_emoji}: **{channel_dict['unknown']}**"
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
        return raid_list, search_label

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
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
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
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
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
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
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
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
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
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=self.bot.guild_dict[ctx.channel.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
        raid_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][ctx.channel.id])
        raid_lobby = raid_dict.get("lobby", None)
        raid_active = raid_dict.get("battling", None)
        raid_complete = raid_dict.get("completed", None)
        list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
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
                    index += 1
                    complete_str += f"**{index}.** "
                    for trainer in lobby['starting_dict'].keys():
                        user = ctx.guild.get_member(trainer)
                        if not user:
                            continue
                        complete_list.append(user.mention)
                    complete_str += ", ".join(complete_list)
                    complete_str += "\n"
                    all_lobbies.append(lobby)
                list_embed.add_field(name="**Completed**", value=complete_str, inline=False)
            if not raid_lobby and not raid_active and not raid_complete:
                list_embed.description = "Nobody has started this raid."
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

    @_list.command(aliases=['boss', 'raidbossses'])
    async def bosses(self, ctx, level=""):
        """List each possible boss and the number of users that have RSVP'd for it if used in a raid channel.
        Otherwise lists possible raid bosses.

        Usage: !list bosses
        Works only in raid channels."""
        if (checks.check_exraidchannel(ctx) or checks.check_raidchannel(ctx)) and checks.check_eggchannel(ctx) and ctx.invoked_with != "raidbosses":
            async with ctx.typing():
                listmsg = _('**Meowth!**')
                listmsg += await self._bosslist(ctx)
                return await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=listmsg))
        else:
            return await self._raidbosslist(ctx, level)

    async def _bosslist(self, ctx):
        message = ctx.message
        channel = ctx.channel
        report_dict = await utils.get_report_dict(ctx.bot, ctx.channel)
        egg_level = self.bot.guild_dict[message.guild.id].setdefault(report_dict, {}).get(channel.id, {}).get('egg_level', None)
        egg_level = str(egg_level)
        if egg_level == "0":
            return await self._raidbosslist(ctx)
        mystic_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['mystic'])
        valor_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['valor'])
        instinct_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict['instinct'])
        unknown_emoji = utils.parse_emoji(ctx.guild, self.bot.config.unknown)
        egg_info = self.bot.raid_info['raid_eggs'][egg_level]
        egg_img = egg_info['egg_img']
        boss_dict = {}
        boss_dict["unspecified"] = {"string": "Unspecified ❔", "total": 0, "maybe": 0, "coming": 0, "here": 0, "mystic": 0, "valor": 0, "instinct": 0, "unknown": 0}
        for boss in self.bot.raid_dict[egg_level]:
            if isinstance(boss, pkmn_class.Pokemon):
                shiny_str = ""
                if boss and "raid" in boss.shiny_available:
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                boss_dict[str(boss).lower()] = {"string": f"{shiny_str}{str(boss)} {boss.emoji}", "total": 0, "maybe": 0, "coming": 0, "here": 0, "mystic": 0, "valor": 0, "instinct": 0, "unknown": 0, "trainers":[]}
        trainer_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id][report_dict][channel.id]['trainer_dict'])
        for trainer in trainer_dict:
            user = ctx.guild.get_member(trainer)
            if not user:
                continue
            interest = trainer_dict[trainer].get('interest', ['unspecified'])
            for item in interest:
                boss_dict[item]['maybe'] += trainer_dict[trainer]['status']['maybe']
                boss_dict[item]['coming'] += trainer_dict[trainer]['status']['coming']
                boss_dict[item]['here'] += trainer_dict[trainer]['status']['here']
                boss_dict[item]['mystic'] += trainer_dict[trainer]['party']['mystic']
                boss_dict[item]['valor'] += trainer_dict[trainer]['party']['valor']
                boss_dict[item]['instinct'] += trainer_dict[trainer]['party']['instinct']
                boss_dict[item]['unknown'] += trainer_dict[trainer]['party']['unknown']
                boss_dict[item]['total'] += sum(trainer_dict[trainer]['party'].values())
                boss_dict[item]['trainers'].append(user.display_name)
        bossliststr = ''
        for boss in boss_dict.keys():
            if boss_dict[boss]['total'] > 0:
                bossliststr += f"{boss_dict[boss]['string']}\n**Total: {boss_dict[boss]['total']}**{' | Maybe: **'+str(boss_dict[boss]['maybe'])+'**' if boss_dict[boss]['maybe'] else ''}{' | Coming: **'+str(boss_dict[boss]['coming'])+'**' if boss_dict[boss]['coming'] else ''}{' | Here: **'+str(boss_dict[boss]['here'])+'**' if boss_dict[boss]['here'] else ''}{' | '+mystic_emoji+': **'+str(boss_dict[boss]['mystic'])+'**' if boss_dict[boss]['mystic'] else ''}{' | '+valor_emoji+' **'+str(boss_dict[boss]['valor'])+'**' if boss_dict[boss]['valor'] else ''}{' | '+instinct_emoji+' **'+str(boss_dict[boss]['instinct'])+'**' if boss_dict[boss]['instinct'] else ''}{' | '+unknown_emoji+' **'+str(boss_dict[boss]['unknown'])+'**' if boss_dict[boss]['unknown'] else ''}\n"
                bossliststr += f"**Trainers:** {', '.join(boss_dict[boss]['trainers'])}\n\n"
        if bossliststr:
            listmsg = _(' Boss numbers for the raid:\n\n{}').format(bossliststr)
        else:
            listmsg = _(' Nobody has told me what boss they want!')
        return listmsg

    async def _raidbosslist(self, ctx, level=""):
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('raid_bosses', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            list_messages = []
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            list_msg = ""
            raid_embed = discord.Embed(colour=ctx.guild.me.colour, title=f"Raid Boss List").set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/raid_tut_raid.png?cache=1')
            if self.bot.raid_info.get('last_edit', False):
                last_edit = datetime.datetime.utcfromtimestamp(self.bot.raid_info['last_edit']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                raid_embed.set_footer(text=f"Last Update: {last_edit.strftime('%B %d at %I:%M %p')}")
            if level.isdigit() and any([level == "1", level == "2", level == "3", level == "4", level == "5", level.lower() == "ex"]):
                level_list = [level.upper()]
            if not level:
                level_list = ["1", "2", "3", "4", "5", "EX"]
            for raid_level in level_list:
                pokemon_list = []
                overwrite_list = []
                for pokemon in self.bot.raid_dict[raid_level]:
                    shiny_str = ""
                    if isinstance(pokemon, pkmn_class.Pokemon):
                        if "raid" in pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        pokemon_list.append(f"{shiny_str}{str(pokemon)} {pokemon.emoji}")
                for overwrite in self.bot.raid_info['raid_eggs'][raid_level].get('overwrites', {}):
                    replace_with = self.bot.raid_info['raid_eggs'][raid_level]['overwrites'][overwrite]['replace_with'] or "None"
                    replace_until = datetime.datetime.utcfromtimestamp(self.bot.raid_info['raid_eggs'][raid_level]['overwrites'][overwrite]['replace_until']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    overwrite_list.append(f"Replacing **{overwrite}** with **{replace_with}** until {replace_until.strftime('%B %d at %I:%M %p')}")
                raid_embed.add_field(name=f"Level {raid_level} Boss List", value=f"{(', ').join(pokemon_list)}\n\n{'**Overwrites**: ' if overwrite_list else ''}{(', ').join(overwrite_list) if overwrite_list else ''}", inline=False)
            msg = await ctx.channel.send(embed=raid_embed)
            list_messages.append(msg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['raid_bosses'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['raid_bosses']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['raid_bosses'][channel]

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
        user_link = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
        user_mute = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('mute', {"raid":False, "invasion":False, "lure":False, "wild":False, "research":False, "nest":False, "trade":False})
        user_wants = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('wants', [])
        user_wants = sorted(user_wants)
        wantlist = [utils.get_name(self.bot, x).title() for x in user_wants]
        user_forms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('forms', [])
        user_bosses = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('bosses', [])
        user_bossforms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('boss_forms', [])
        user_bosses = sorted(user_bosses)
        bosslist = [utils.get_name(self.bot, x).title() for x in user_bosses]
        user_trades = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('trades', [])
        user_tradeforms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('trade_forms', [])
        tradelist = [utils.get_name(self.bot, x).title() for x in user_trades]
        user_gyms = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('gyms', [])
        user_gyms = [x.title() for x in user_gyms]
        user_stops = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('stops', [])
        user_stops = [x.title() for x in user_stops]
        user_items = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('items', [])
        user_items = [x.title() for x in user_items]
        user_types = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('types', [])
        user_types = [x.title() for x in user_types]
        user_eggs = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('raid_eggs', [])
        user_ivs = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('ivs', [])
        user_ivs = sorted(user_ivs)
        user_ivs = [str(x) for x in user_ivs]
        user_levels = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('levels', [])
        user_levels = sorted(user_levels)
        user_levels = [str(x) for x in user_levels]
        user_cps = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('cps', [])
        user_cps = sorted(user_cps)
        user_cps = [str(x) for x in user_cps]
        user_custom = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('custom', {})
        alert_text = ""
        for custom in user_custom:
            alert_text += f"**Pokemon**: {user_custom[custom]['pokemon']}"
            if user_custom[custom].get('min_iv'):
                alert_text += f" | **IV Percent**: {user_custom[custom]['min_iv']}-{user_custom[custom]['max_iv']}"
            if user_custom[custom].get('min_atk'):
                alert_text += f" | **IV Attack**: {user_custom[custom]['min_atk']}-{user_custom[custom]['max_atk']}"
            if user_custom[custom].get('min_def'):
                alert_text += f" | **IV Defense**: {user_custom[custom]['min_def']}-{user_custom[custom]['max_def']}"
            if user_custom[custom].get('min_sta'):
                alert_text += f" | **IV Stamina**: {user_custom[custom]['min_sta']}-{user_custom[custom]['max_sta']}"
            if user_custom[custom].get('min_cp'):
                alert_text += f" | **CP**: {user_custom[custom]['min_cp']}-{user_custom[custom]['max_cp']}"
            if user_custom[custom].get('min_level'):
                alert_text += f" | **Level**: {user_custom[custom]['min_level']}-{user_custom[custom]['max_level']}"
            if user_custom[custom].get('gender'):
                alert_text += f" | **Gender**: {user_custom[custom]['gender']}"
            if user_custom[custom].get('size'):
                alert_text += f" | **Size**: {user_custom[custom]['size']}"
            alert_text += f" | **Report Types**: {(', ').join(user_custom[custom]['report_types'])}\n"
        custom_list = alert_text.splitlines()
        categories = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('categories', {}))
        pokemon_options = ["wild", "research", "invasion", "nest", "trade", "raid"]
        pokestop_options = ["research", "wild", "lure", "invasion"]
        type_options = ["wild", "research", "nest", "invasion", "raid", "trade"]
        item_options = ["research", "lure"]
        pokemon_settings = categories.get('pokemon', {})
        if not pokemon_settings:
            pokemon_settings = {k:True for k in pokemon_options}
        pokestop_settings = categories.get('stop', {})
        if not pokestop_settings:
            pokestop_settings = {k:True for k in pokestop_options}
        item_settings = categories.get('item', {})
        if not item_settings:
            item_settings = {k:True for k in item_options}
        type_settings = categories.get('type', {})
        if not type_settings:
            type_settings = {k:True for k in type_options}
        if not user_link:
            pokemon_settings['raid'] = False
            pokemon_settings['trade'] = False
        wantmsg = ""
        if len(wantlist) > 0 or len(user_gyms) > 0 or len(user_stops) > 0 or len(user_items) > 0 or len(bosslist) > 0 or len(user_types) > 0 or len(user_ivs) > 0 or len(user_levels) or len(user_cps) > 0 or len(user_forms) > 0 or len(user_eggs) > 0:
            if wantlist:
                wantmsg += f"**Pokemon:** ({(', ').join([x for x in pokemon_options if pokemon_settings.get(x)])})\n{', '.join(wantlist)}\n\n"
            if user_forms:
                wantmsg += f"**Pokemon Forms:** ({(', ').join([x for x in pokemon_options if pokemon_settings.get(x)])})\n{', '.join(user_forms)}\n\n"
            if user_bosses and not user_link:
                wantmsg += f"**Bosses:** (raids)\n{', '.join(bosslist)}\n\n"
            if user_bossforms and not user_link:
                wantmsg += f"**Boss Forms:** (raids)\n{', '.join(user_bossforms)}\n\n"
            if (user_trades or user_tradeforms) and not user_link:
                wantmsg += f"**Trades:** (trades)\n{', '.join(tradelist+user_tradeforms)}\n\n"
            if custom_list:
                wantmsg += f"**Custom:**\n"+('\n').join(custom_list)+"\n\n"
            if user_gyms:
                wantmsg += f"**Gyms:** (raid)\n{', '.join(user_gyms)}\n\n"
            if user_stops:
                wantmsg += f"**Stops:** ({(', ').join([x for x in pokestop_options if pokestop_settings.get(x)])})\n{', '.join(user_stops)}\n\n"
            if user_items:
                wantmsg += f"**Items:** ({(', ').join([x for x in item_options if item_settings.get(x)])})\n{', '.join(user_items)}\n\n"
            if user_types:
                wantmsg += f"**Types:** ({(', ').join([x for x in type_options if type_settings.get(x)])})\n{', '.join(user_types)}\n\n"
            if user_ivs:
                wantmsg += f"**IVs:** (wilds)\n{', '.join(user_ivs)}\n\n"
            if user_levels:
                wantmsg += f"**Levels:** (wilds)\n{', '.join(user_levels)}\n\n"
            if user_cps:
                wantmsg += f"**CPs:** (wilds)\n{', '.join(user_cps)}\n\n"
            if user_eggs:
                wantmsg += f"**Raid Eggs:** (raids)\n{', '.join(user_eggs)}\n\n"
        if wantmsg:
            if any(list(user_mute.values())):
                listmsg = f"Meowth! {ctx.author.display_name}, your **{(', ').join([x for x in user_mute if user_mute[x]])}** notifications are muted, so you will not receive those notifications from your current **!want** list:"
            else:
                listmsg = _('Meowth! {author}, you will receive notifications for your current **!want** list:').format(author=ctx.author.display_name)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wantmsg.splitlines():
                if len(line) < 1900:
                    paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                else:
                    new_list = []
                    line_split = line.split(',')
                    line_split = [x.strip() for x in line_split]
                    for item in line_split:
                        if len(f"{(', ').join(new_list)}") < 1900:
                            new_list.append(item)
                        else:
                            paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
                            new_list = []
                    if new_list:
                        paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
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
        bossform_list = []
        trade_list = []
        item_list = []
        type_list = []
        iv_list = []
        level_list = []
        cp_list = []
        raidegg_list = []
        custom_list = []
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('wants', []):
                if want not in want_list:
                    want_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('forms', []):
                if want not in form_list:
                    form_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('custom', {}):
                pokemon = self.bot.guild_dict[ctx.guild.id]['trainers'][trainer]['alerts']['custom'][want]['pokemon']
                if pokemon not in custom_list:
                    custom_list.append(pokemon)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('stops', []):
                if want not in stop_list:
                    stop_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('gyms', []):
                if want not in gym_list:
                    gym_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('bosses', []):
                if want not in boss_list:
                    boss_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('boss_forms', []):
                if want not in bossform_list:
                    bossform_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('trades', []):
                if want not in trade_list:
                    trade_list.append(utils.get_name(self.bot, want))
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('trade_forms', []):
                if want not in trade_list:
                    trade_list.append(want)
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
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('cps', []):
                if want not in cp_list:
                    cp_list.append(want)
            for want in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].setdefault('alerts', {}).setdefault('raid_eggs', []):
                if want not in raidegg_list:
                    raidegg_list.append(want)
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
        cp_list = sorted(cp_list)
        cp_list = [str(x) for x in cp_list]
        raidegg_list = sorted([int(x) for x in raidegg_list])
        raidegg_list = [str(x) for x in raidegg_list]
        wantmsg = ""
        if want_list or gym_list or stop_list or item_list or boss_list or type_list or iv_list or level_list or cp_list or custom_list:
            if want_list:
                wantmsg += f"**Pokemon:**\n{', '.join(want_list)}\n\n"
            if form_list:
                wantmsg += f"**Pokemon Forms:**\n{', '.join(form_list)}\n\n"
            if boss_list:
                wantmsg += f"**Bosses:**\n{', '.join(boss_list)}\n\n"
            if bossform_list:
                wantmsg += f"**Boss Forms:**\n{', '.join(bossform_list)}\n\n"
            if trade_list:
                wantmsg += f"**Trades:**\n{', '.join(trade_list)}\n\n"
            if custom_list:
                wantmsg += f"**Custom:**\n{', '.join(custom_list)}\n\n"
            if gym_list:
                wantmsg += f"**Gyms:**\n{', '.join(gym_list)}\n\n"
            if stop_list:
                wantmsg += f"**Stops:**\n{', '.join(stop_list)}\n\n"
            if item_list:
                wantmsg += f"**Items:**\n{', '.join(item_list)}\n\n"
            if type_list:
                wantmsg += f"**Types:**\n{', '.join(type_list)}\n\n"
            if iv_list:
                wantmsg += f"**IVs:**\n{', '.join(iv_list)}\n\n"
            if level_list:
                wantmsg += f"**Levels:**\n{', '.join(level_list)}\n\n"
            if cp_list:
                wantmsg += f"**CPs:**\n{', '.join(cp_list)}\n\n"
            if raidegg_list:
                wantmsg += f"**Raid Eggs:**\n{', '.join(raidegg_list)}\n\n"
        if wantmsg:
            listmsg = _('**Meowth!** The server **!want** list is:')
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wantmsg.splitlines():
                if len(line) < 1900:
                    paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                else:
                    new_list = []
                    line_split = line.split(',')
                    line_split = [x.strip() for x in line_split]
                    for item in line_split:
                        if len(f"{(', ').join(new_list)}") < 1900:
                            new_list.append(item)
                        else:
                            paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
                            new_list = []
                    if new_list:
                        paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("**Meowth!** Nobody has any wants! use **!want** to add some.")
        return listmsg, None

    @_list.command(aliases=['trade'])
    @checks.allowtrade()
    async def trades(self, ctx, *, search=None):
        """List the trades for the user or pokemon

        Usage: !list trades [user or pokemon or shiny]
        Works only in trading channels. Will search for supplied search term, showing
        all pokemon that match or all trades for specific user"""
        async with ctx.typing():
            delete_list = []
            if not search:
                search = ctx.author
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
                if pokemon:
                    search = str(pokemon)
                elif "shiny" in search.lower():
                    search = "shiny"
                elif "all" in search.lower():
                    search = "all"
                    list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('trade', {}).setdefault(ctx.channel.id, [])
                    delete_list = []
                    for msg in list_dict:
                        try:
                            msg = await ctx.channel.fetch_message(msg)
                            delete_list.append(msg)
                        except:
                            pass
                    await utils.safe_bulk_delete(ctx.channel, delete_list)
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
                            profile = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {})
                            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trade_list'] = {ctx.channel.id: listmsg.id}
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
                if search == "all":
                    self.bot.guild_dict[ctx.guild.id]['list_dict']['trade'][ctx.channel.id] = list_messages
                    for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['trade']):
                        if not ctx.guild.get_channel(channel):
                            del self.bot.guild_dict[ctx.guild.id]['list_dict']['trade'][channel]
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return

    async def _tradelist(self, ctx, search):
        tgt_trainer_trades = {}
        tgt_pokemon_trades = {}
        tgt_shiny_trades = {}
        tgt_all_trades = {}
        target_trades = {}
        listmsg = ""
        trademsg = ""
        lister_str = ""
        shiny_emoji = self.bot.custom_emoji.get('shiny_chance', u'\U00002728')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
        for offer_id in self.bot.guild_dict[ctx.guild.id]['trade_dict']:
            if self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['report_channel_id'] != ctx.channel.id:
                continue
            if search == "all":
                tgt_all_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
            elif isinstance(search, discord.member.Member):
                if self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['lister_id'] == search.id:
                    tgt_trainer_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
            elif search == "shiny":
                if "shiny" in self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['offered_pokemon'].lower():
                    tgt_shiny_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
            else:
                if str(pokemon) in self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]['offered_pokemon']:
                    tgt_pokemon_trades[offer_id] = self.bot.guild_dict[ctx.guild.id]['trade_dict'][offer_id]
        if tgt_trainer_trades:
            listmsg = _("Meowth! Here are the current trades for {user}:").format(user=search.display_name)
        elif tgt_pokemon_trades:
            listmsg = _("Meowth! Here are the current {pokemon} trades:").format(pokemon=str(pokemon))
        elif tgt_shiny_trades:
            listmsg = _("Meowth! Here are the current Shiny trades:")
        elif tgt_all_trades:
            listmsg = f"Meowth! Here are all active trades in {ctx.channel.mention}:"
        target_trades = {**tgt_trainer_trades, **tgt_shiny_trades, **tgt_pokemon_trades, **tgt_all_trades}
        if target_trades:
            for offer_id in target_trades:
                offer_url = ""
                try:
                    offer_channel = self.bot.get_channel(
                        target_trades[offer_id]['report_channel_id'])
                    offer_url = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{offer_id}"
                except:
                    continue
                lister = ctx.guild.get_member(target_trades[offer_id]['lister_id'])
                if not lister:
                    continue
                lister_str = f"**Lister**: {lister.display_name}"
                offered_pokemon = target_trades[offer_id]['offered_pokemon']
                offered_pokemon = await pkmn_class.Pokemon.async_get_pokemon(ctx.bot, offered_pokemon)
                offered_pokemon = f"{str(offered_pokemon)} {offered_pokemon.emoji}"
                offered_pokemon = offered_pokemon.replace("Shiny", f"{shiny_emoji} Shiny")
                wanted_pokemon = target_trades[offer_id]['wanted_pokemon']
                if "Open Trade" in wanted_pokemon or not wanted_pokemon:
                    wanted_pokemon = "Open Trade (DM User)"
                else:
                    wanted_pokemon = str(wanted_pokemon).encode('ascii', 'ignore').decode("utf-8").replace(":", "")
                    wanted_pokemon = ''.join(x for x in wanted_pokemon if not x.isdigit())
                    wanted_pokemon = [x.strip() for x in wanted_pokemon.split("\n")]
                    wanted_pokemon = ', '.join(wanted_pokemon)
                trade_details = target_trades[offer_id].get('details', '')
                trademsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('trade_bullet', u'\U0001F539')))
                trademsg += (f"**Offered Pokemon**: {offered_pokemon} | **Wanted Pokemon**: {wanted_pokemon}{' | **Details**: '+trade_details if trade_details else ''} | {lister_str} | [Jump To Message]({offer_url})")
        if trademsg:
            paginator = commands.Paginator(prefix="", suffix="")
            for line in trademsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = f"Meowth! No active trades matched your search term **{search}**. List one with **!trade**"
        return listmsg, None

    @_list.command(aliases=['looking'])
    @checks.allowtrade()
    async def searching(self, ctx, *, search=None):
        """List the trades for the user or pokemon

        Usage: !list trades [user or pokemon or shiny]
        Works only in trading channels. Will search for supplied search term, showing
        all pokemon that match or all trades for specific user"""
        async with ctx.typing():
            delete_list = []
            if not search:
                search = ctx.author
            else:
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
                if pokemon:
                    search = str(pokemon)
                elif "shiny" in search.lower():
                    search = "shiny"
                elif "all" in search.lower():
                    search = "all"
                    list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('trade_search', {}).setdefault(ctx.channel.id, [])
                    delete_list = []
                    for msg in list_dict:
                        try:
                            msg = await ctx.channel.fetch_message(msg)
                            delete_list.append(msg)
                        except:
                            pass
                    await utils.safe_bulk_delete(ctx.channel, delete_list)
                else:
                    converter = commands.MemberConverter()
                    try:
                        search = await converter.convert(ctx, search)
                    except Exception as e:
                        search = ctx.author
            listmsg, res_pages = await self._searchoflist(ctx, search)
            list_messages = []
            if res_pages:
                index = 0
                for p in res_pages:
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                        if search == ctx.author:
                            profile = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {})
                            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trade_list'] = {ctx.channel.id: listmsg.id}
                    else:
                        listmsg = await ctx.channel.send(embed=discord.Embed(colour=ctx.guild.me.colour, description=p))
                    list_messages.append(listmsg.id)
                    index += 1
                if search == "all":
                    self.bot.guild_dict[ctx.guild.id]['list_dict']['trade_search'][ctx.channel.id] = list_messages
                    for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['trade_search']):
                        if not ctx.guild.get_channel(channel):
                            del self.bot.guild_dict[ctx.guild.id]['list_dict']['trade_search'][channel]
            elif listmsg:
                listmsg = await ctx.channel.send(listmsg)
                list_messages.append(listmsg.id)
            else:
                return

    async def _searchoflist(self, ctx, search):
        tgt_trainer_trades = {}
        tgt_pokemon_trades = {}
        tgt_shiny_trades = {}
        tgt_all_trades = {}
        target_trades = {}
        all_wants = {}
        listmsg = ""
        trademsg = ""
        shiny_emoji = self.bot.custom_emoji.get('shiny_chance', u'\U00002728')
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search)
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            if isinstance(search, discord.member.Member):
                trainer = search.id
            user_link = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('alerts', {}).setdefault('settings', {}).setdefault('link', True)
            if user_link:
                user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
                trade_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('trade', False)
            else:
                user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('trades', [])
                user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('trade_forms', [])
                trade_setting = True
            if not trade_setting:
                continue
            for want in user_wants:
                if ("shiny" in str(want).lower() and search == "shiny") or search == "all" or isinstance(search, discord.member.Member):
                    all_wants[utils.get_name(self.bot, want)] = want
            for want in user_forms:
                shiny_str = ""
                if "shiny" in want.lower():
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                for word in want.split():
                    if word.lower() in self.bot.pkmn_list:
                        if ("shiny" in want.lower() and search == "shiny") or search == "all" or isinstance(search, discord.member.Member):
                            all_wants[f"{shiny_str}{want.lower()}"] = utils.get_number(self.bot, word)
            if isinstance(search, discord.member.Member):
                break
        all_wants = dict(sorted(all_wants.items(), key=lambda x: x[1]))
        if all_wants and isinstance(search, discord.member.Member):
            listmsg = f"Meowth! Here are the pokemon that {search.display_name} is looking for!"
            trademsg = f"**Pokemon:**\n\n{(', ').join([x.title() for x in all_wants.keys()])}"
        elif all_wants:
            listmsg = f"Meowth! Here are the current{' shiny' if search == 'shiny' else ''} pokemon that users are searching for!"
            trademsg = f"**Pokemon:**\n\n{(', ').join([x.title() for x in all_wants.keys()])}"
        if trademsg:
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wantmsg.splitlines():
                if len(line) < 1900:
                    paginator.add_line(line.rstrip().replace('`', '\u200b`'))
                else:
                    new_list = []
                    line_split = line.split(',')
                    line_split = [x.strip() for x in line_split]
                    for item in line_split:
                        if len(f"{(', ').join(new_list)}") < 1900:
                            new_list.append(item)
                        else:
                            paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
                            new_list = []
                    if new_list:
                        paginator.add_line((', ').join(new_list).rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = f"Meowth! No active trades matched your search term **{search}**. List one with **!trade**"
        return listmsg, None

    @_list.command(aliases=['res'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowresearchreport()
    async def research(self, ctx, *, search_term="all"):
        """List the quests for the channel

        Usage: !list research

        Research Reporting Channel Listing Options: pokemon, location, type, item"""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'research']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "research reports"
        if search_term != "all":
            pois = {}
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            if gym_matching_cog:
                pois = {**gym_matching_cog.get_stops(ctx.guild.id), **gym_matching_cog.get_gyms(ctx.guild.id)}
                pois = {k.lower(): v for k, v in pois.items()}
            search_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search_term)
            search_item = await utils.get_item(search_term)
            if search_term in self.bot.type_list:
                search_term = search_term
                search_label = f"{search_term.title()} type research reports"
            elif search_term in [x.lower() for x in pois.keys()]:
                if pois[search_term].get('alias'):
                    search_term = pois[search_term].get('alias')
                search_label = f"research reports at {search_term.title()}"
            elif search_pokemon:
                search_term = search_pokemon.name.lower()
                search_label = f"{search_term.title()} research reports"
            elif search_item[1]:
                search_term = search_item[1]
                search_label = f"{search_term.title()} research reports"
            else:
                search_term = "all"
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
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('research_report', u'\U0001F4E2')
            listmsg, res_pages = await self._researchlist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if res_pages:
                index = 0
                for p in res_pages:
                    list_embed.description = p
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('research_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current {search_label.title()}**", value=f"Meowth! There are no reported {search_label}. Report one with **{ctx.prefix}research <pokestop>, <quest>, <reward>** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['research'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['research']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['research'][channel]

    async def _researchlist(self, ctx, search_term="all"):
        research_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('questreport_dict', {}))
        quest_dict = {'encounters':{}, 'candy':{}, 'dust':{}, 'berry':{}, 'potion':{}, 'revive':{}, 'ball':{}, 'other':{}}
        reward_dict = {'encounters':[], 'candy':[], 'dust':[], 'berry':[], 'potion':[], 'revive':[], 'ball':[], 'other':[]}
        questmsg = ""
        search_label = "research reports"
        item_quests = []
        encounter_quests = []
        dust_quests = []
        candy_quests = []
        berry_quests = []
        potion_quests = []
        revive_quests = []
        ball_quests = []
        reward_list = ["ball", "nanab", "pinap", "razz", "berr", "stardust", "potion", "revive", "candy", "lure", "module", "mysterious", "component", "radar", "sinnoh", "unova", "stone", "scale", "coat", "grade"]
        encounter_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_encounter', u'\U00002753'))
        candy_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_candy', u'\U0001F36C'))
        dust_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_dust', u'\U00002b50'))
        berry_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_berry', u'\U0001F353'))
        potion_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_potion', u'\U0001F48A'))
        revive_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_revive', u'\U00002764\U0000fe0f'))
        ball_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_ball', u'\U000026be'))
        other_emoji = utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('res_other', u'\U0001F539'))
        for questid in research_dict:
            pokemon = None
            condition_check = research_dict[questid]['report_channel'] == ctx.channel.id
            if "dm" in str(ctx.invoked_with):
                condition_check = ctx.author.id in research_dict[questid].get('dm_dict')
            if condition_check:
                try:
                    questauthor = ctx.guild.get_member(research_dict[questid]['report_author'])
                    reported_by = ""
                    if questauthor and not questauthor.bot:
                        reported_by = f" | **Reported By**: {questauthor.display_name}"
                    quest = research_dict[questid]['quest']
                    reward = research_dict[questid]['reward']
                    location = research_dict[questid]['location']
                    url = research_dict[questid].get('url', None)
                    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{research_dict[questid]['report_channel']}/{questid}"
                    if questid in self.bot.active_research:
                        pokemon = self.bot.active_research[questid]
                    else:
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, reward)
                        self.bot.active_research[questid] = pokemon
                    other_reward = any(x in reward for x in reward_list)
                    type_list = []
                    if pokemon and not other_reward:
                        type_list.extend(pokemon.types)
                    if search_term != "all":
                        if str(getattr(pokemon, 'name', None)).lower() == search_term:
                            search_label = f"{search_term.title()} research reports"
                        elif search_term in reward.lower():
                            search_label = f"{search_term.title()} research reports"
                        elif search_term.title() in type_list:
                            search_label = f"{search_term.title()} type research reports"
                        elif search_term.lower() == location.lower():
                            search_label = f"research reports at {search_term.title()}"
                        else:
                            continue
                    type_list = []
                    if pokemon and not other_reward:
                        shiny_str = ""
                        if pokemon and "research" in pokemon.shiny_available:
                            shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                        quest_dict['encounters'][questid] = {"reward":f"{shiny_str}{reward} {pokemon.emoji}", "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "pokemon":pokemon.name, "jump_url":jump_url}
                        if pokemon.name not in reward_dict['encounters']:
                            reward_dict['encounters'].append(pokemon.name)
                    elif "candy" in reward.lower() or "candies" in reward.lower():
                        quest_dict['candy'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['candy']:
                            reward_dict['candy'].append(reward)
                    elif "dust" in reward.lower():
                        quest_dict['dust'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['dust']:
                            reward_dict['dust'].append(reward)
                    elif "berry" in reward.lower() or "berries" in reward.lower() or "razz" in reward.lower() or "pinap" in reward.lower() or "nanab" in reward.lower():
                        quest_dict['berry'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['berry']:
                            reward_dict['berry'].append(reward)
                    elif "potion" in reward.lower():
                        quest_dict['potion'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['potion']:
                            reward_dict['potion'].append(reward)
                    elif "revive" in reward.lower():
                        quest_dict['revive'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['revive']:
                            reward_dict['revive'].append(reward)
                    elif "ball" in reward.lower():
                        quest_dict['ball'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['ball']:
                            reward_dict['ball'].append(reward)
                    else:
                        quest_dict['other'][questid] = {"reward":reward, "location":f"[{string.capwords(location, ' ')}]({url})", "quest":f"{string.capwords(quest, ' ')}", "reporter":reported_by, "url":url, "jump_url":jump_url}
                        if reward not in reward_dict['other']:
                            reward_dict['other'].append(reward)
                except:
                    continue
        for pkmn in sorted(reward_dict['encounters']):
            for quest in quest_dict['encounters']:
                if quest_dict['encounters'][quest]['pokemon'] == pkmn and not quest_dict['encounters'][quest].get('listed', False):
                    encounter_quests.append(f"{encounter_emoji} **Reward**: {quest_dict['encounters'][quest]['reward']} | **Pokestop**: {quest_dict['encounters'][quest]['location']} | **Quest**: {quest_dict['encounters'][quest]['quest']}{quest_dict['encounters'][quest]['reporter']} | [Jump to Report]({quest_dict['encounters'][quest]['jump_url']})")
                    quest_dict['encounters'][quest]['listed'] = True
        if encounter_quests:
            questmsg += "\n\n**Pokemon Encounters**\n{encounterlist}".format(encounterlist="\n".join(encounter_quests))
        for candy in sorted(reward_dict['candy']):
            for quest in quest_dict['candy']:
                if quest_dict['candy'][quest]['reward'] == candy and not quest_dict['candy'][quest].get('listed', False):
                    candy_quests.append(f"{candy_emoji} **Reward**: {quest_dict['candy'][quest]['reward'].title()} | **Pokestop**: {quest_dict['candy'][quest]['location']} | **Quest**: {quest_dict['candy'][quest]['quest']}{quest_dict['candy'][quest]['reporter']} | [Jump to Report]({quest_dict['candy'][quest]['jump_url']})")
                    quest_dict['candy'][quest]['listed'] = True
        if candy_quests:
            questmsg += "\n\n**Rare Candy**\n{candylist}".format(candylist="\n".join(candy_quests))
        for berry in sorted(reward_dict['berry']):
            for quest in quest_dict['berry']:
                if quest_dict['berry'][quest]['reward'] == berry and not quest_dict['berry'][quest].get('listed', False):
                    berry_quests.append(f"{berry_emoji} **Reward**: {quest_dict['berry'][quest]['reward'].title()} | **Pokestop**: {quest_dict['berry'][quest]['location']} | **Quest**: {quest_dict['berry'][quest]['quest']}{quest_dict['berry'][quest]['reporter']} | [Jump to Report]({quest_dict['berry'][quest]['jump_url']})")
                    quest_dict['berry'][quest]['listed'] = True
        if berry_quests:
            questmsg += "\n\n**Berries**\n{itemlist}".format(itemlist="\n".join(berry_quests))
        for potion in sorted(reward_dict['potion']):
            for quest in quest_dict['potion']:
                if quest_dict['potion'][quest]['reward'] == potion and not quest_dict['potion'][quest].get('listed', False):
                    potion_quests.append(f"{potion_emoji} **Reward**: {quest_dict['potion'][quest]['reward'].title()} | **Pokestop**: {quest_dict['potion'][quest]['location']} | **Quest**: {quest_dict['potion'][quest]['quest']}{quest_dict['potion'][quest]['reporter']} | [Jump to Report]({quest_dict['potion'][quest]['jump_url']})")
                    quest_dict['potion'][quest]['listed'] = True
        if potion_quests:
            questmsg += "\n\n**Potions**\n{itemlist}".format(itemlist="\n".join(potion_quests))
        for revive in sorted(reward_dict['revive']):
            for quest in quest_dict['revive']:
                if quest_dict['revive'][quest]['reward'] == revive and not quest_dict['revive'][quest].get('listed', False):
                    revive_quests.append(f"{revive_emoji} **Reward**: {quest_dict['revive'][quest]['reward'].title()} | **Pokestop**: {quest_dict['revive'][quest]['location']} | **Quest**: {quest_dict['revive'][quest]['quest']}{quest_dict['revive'][quest]['reporter']} | [Jump to Report]({quest_dict['revive'][quest]['jump_url']})")
                    quest_dict['revive'][quest]['listed'] = True
        if revive_quests:
            questmsg += "\n\n**Revives**\n{itemlist}".format(itemlist="\n".join(revive_quests))
        for ball in sorted(reward_dict['ball']):
            for quest in quest_dict['ball']:
                if quest_dict['ball'][quest]['reward'] == ball and not quest_dict['ball'][quest].get('listed', False):
                    ball_quests.append(f"{ball_emoji} **Reward**: {quest_dict['ball'][quest]['reward'].title()} | **Pokestop**: {quest_dict['ball'][quest]['location']} | **Quest**: {quest_dict['ball'][quest]['quest']}{quest_dict['ball'][quest]['reporter']} | [Jump to Report]({quest_dict['ball'][quest]['jump_url']})")
                    quest_dict['ball'][quest]['listed'] = True
        if ball_quests:
            questmsg += "\n\n**Poke Balls**\n{itemlist}".format(itemlist="\n".join(ball_quests))
        for item in sorted(reward_dict['other']):
            for quest in quest_dict['other']:
                if quest_dict['other'][quest]['reward'] == item and not quest_dict['other'][quest].get('listed', False):
                    item_quests.append(f"{other_emoji} **Reward**: {quest_dict['other'][quest]['reward'].title()} | **Pokestop**: {quest_dict['other'][quest]['location']} | **Quest**: {quest_dict['other'][quest]['quest']}{quest_dict['other'][quest]['reporter']} | [Jump to Report]({quest_dict['other'][quest]['jump_url']})")
                    quest_dict['other'][quest]['listed'] = True
        if item_quests:
            questmsg += "\n\n**Other Rewards**\n{itemlist}".format(itemlist="\n".join(item_quests))
        for dust in sorted(reward_dict['dust']):
            for quest in quest_dict['dust']:
                if quest_dict['dust'][quest]['reward'] == dust and not quest_dict['dust'][quest].get('listed', False):
                    dust_quests.append(f"{dust_emoji} **Reward**: {quest_dict['dust'][quest]['reward'].title()} | **Pokestop**: {quest_dict['dust'][quest]['location']} | **Quest**: {quest_dict['dust'][quest]['quest']}{quest_dict['dust'][quest]['reporter']} | [Jump to Report]({quest_dict['dust'][quest]['jump_url']})")
                    quest_dict['dust'][quest]['listed'] = True
        if dust_quests:
            questmsg += "\n\n**Stardust**\n{dustlist}".format(dustlist="\n".join(dust_quests))
        if questmsg:
            listmsg = f"**Meowth! Here's the current {search_label} for {getattr(ctx.channel, 'mention', 'this channel')}**"
            report_emoji = self.bot.custom_emoji.get('research_report', u'\U0001F4E2')
            questmsg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new research report!"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in questmsg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    @_list.command(aliases=['task'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def tasks(self, ctx, list_type="all"):
        """List the current research tasks

        Usage: !list tasks [all / pokemon / items]"""
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('res_tasks', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            list_messages = []
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            research_embed = discord.Embed(discription="", colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/ui/field-research.png?cache=1')
            if self.bot.quest_info.get('last_edit', False):
                last_edit = datetime.datetime.utcfromtimestamp(self.bot.quest_info['last_edit']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                research_embed.set_footer(text=f"Last Update: {last_edit.strftime('%B %d at %I:%M %p')}")
            if not any([list_type == "all", list_type == "pokemon", list_type == "items"]):
                list_type = "all"
            for category in self.bot.quest_info[list_type].keys():
                field_value = ""
                for quest in self.bot.quest_info[list_type][category]:
                    if (len(field_value) + len(f"**{quest}** - {(', ').join([x.title() for x in self.bot.quest_info[list_type][category][quest]])}\n")) >= 1020:
                        research_embed.add_field(name=category, value=field_value, inline=False)
                        msg = await ctx.send(embed=research_embed)
                        list_messages.append(msg.id)
                        research_embed.clear_fields()
                        field_value = ""
                    field_value += f"**{quest}** - {(', ').join([x.title() for x in self.bot.quest_info[list_type][category][quest]])}\n"
                research_embed.add_field(name=category, value=field_value, inline=False)
            msg = await ctx.send(embed=research_embed)
            list_messages.append(msg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['res_tasks'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['res_tasks']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['res_tasks'][channel]

    @_list.command(aliases=['egg'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def eggs(self, ctx, level=""):
        """List the current egg distances

        Usage: !list eggs"""
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('egg_list', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            list_messages = []
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            egg_embed = discord.Embed(discription="", colour=ctx.guild.me.colour)
            if self.bot.egg_info.get('last_edit', False):
                last_edit = datetime.datetime.utcfromtimestamp(self.bot.egg_info['last_edit']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                egg_embed.set_footer(text=f"Last Update: {last_edit.strftime('%B %d at %I:%M %p')}")
            if level.isdigit() and any([level == "2", level == "5", level == "7", level == "10"]):
                distance_list = level
            if not level:
                distance_list = ["2", "5", "7", "10"]
            for egg_distance in self.bot.egg_info.keys():
                if egg_distance not in distance_list:
                    continue
                egg_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/eggs/{egg_distance}km.png?cache=1")
                current_length = 0
                egg_list = []
                for item in self.bot.egg_info[egg_distance]:
                    if len(item) + current_length < 900:
                        egg_list.append(item)
                        current_length += len(item)
                    else:
                        egg_embed.add_field(name=f"{egg_distance}KM Eggs", value=(', ').join(egg_list), inline=False)
                        current_length = 0
                        egg_list = []
                if egg_list:
                    egg_embed.add_field(name=f"{egg_distance}KM Eggs", value=(', ').join(egg_list), inline=False)
                msg = await ctx.send(embed=egg_embed)
                egg_embed.clear_fields()
                list_messages.append(msg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['egg_list'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['egg_list']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['egg_list'][channel]

    @_list.command(aliases=['lure'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowlurereport()
    async def lures(self, ctx, *, search_term="all"):
        """List the lures for the channel

        Usage: !list lures

        Lure Reporting Channel Listing Options: lure type, location"""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'lures']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "lure reports"
        if search_term != "all":
            pois = {}
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            if gym_matching_cog:
                pois = {**gym_matching_cog.get_stops(ctx.guild.id), **gym_matching_cog.get_gyms(ctx.guild.id)}
                pois = {k.lower(): v for k, v in pois.items()}
            if search_term in ["normal", "mossy", "glacial", "magnetic"]:
                search_label = f"{search_term.title()} lure reports"
            elif search_term in [x.lower() for x in pois]:
                if pois[search_term].get('alias'):
                    search_term = pois[search_term].get('alias')
                search_label = f"lure reports at {search_term.title()}"
            else:
                search_term = "all"
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
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('lure_report', u'\U0001F4E2')
            listmsg, lure_pages = await self._lurelist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if lure_pages:
                index = 0
                for p in lure_pages:
                    list_embed.description = p
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('lure_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current {search_label.title()}**", value=f"Meowth! There are no reported {search_label}. Report one with **{ctx.prefix}lure <type> <location>** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['lure'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['lure']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['lure'][channel]

    async def _lurelist(self, ctx, search_term="all"):
        lure_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('lure_dict', {}))
        listing_dict = {}
        normal_emoji = self.bot.custom_emoji.get('normal_lure', self.bot.config.type_id_dict['normal'])
        glacial_emoji = self.bot.custom_emoji.get('glacial_lure', self.bot.config.type_id_dict['ice'])
        mossy_emoji = self.bot.custom_emoji.get('mossy_lure', self.bot.config.type_id_dict['grass'])
        magnetic_emoji = self.bot.custom_emoji.get('normal_lure', self.bot.config.type_id_dict['steel'])
        search_label = ""
        for lureid in lure_dict:
            luremsg = ""
            condition_check = lure_dict[lureid]['report_channel'] == ctx.channel.id
            if "dm" in str(ctx.invoked_with):
                condition_check = ctx.author.id in lure_dict[lureid].get('dm_dict', {})
            if condition_check:
                try:
                    lureauthor = ctx.guild.get_member(lure_dict[lureid]['report_author'])
                    lure_expire = datetime.datetime.utcfromtimestamp(lure_dict[lureid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    lure_type = lure_dict[lureid]['type']
                    location = lure_dict[lureid]['location']
                    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{lure_dict[lureid]['report_channel']}/{lureid}"
                    if search_term != "all":
                        if lure_type == search_term:
                            search_label = f"{search_term.title()} lure reports"
                        elif search_term == location.lower():
                            search_label = f"lure reports at {search_term.title()}"
                        else:
                            continue
                    reported_by = ""
                    if lureauthor and not lureauthor.bot:
                        reported_by = f" | **Reported By**: {lureauthor.display_name}"
                    luremsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('lure_bullet', u'\U0001F539')))
                    luremsg += f"**Lure Type**: {lure_type.title()} {normal_emoji if lure_type == 'normal' else ''}{glacial_emoji if lure_type == 'glacial' else ''}{mossy_emoji if lure_type == 'mossy' else ''}{magnetic_emoji if lure_type == 'magnetic' else ''} | **Location**: [{string.capwords(location, ' ')}]({lure_dict[lureid].get('url', None)}) | **Expires**: {lure_expire.strftime(_('%I:%M %p'))}{reported_by} | [Jump to Report]({jump_url})"
                    listing_dict[lureid] = {
                        "message":luremsg,
                        "expire":lure_expire
                    }
                except Exception as e:
                    print("lurelist", e)
                    continue
        if listing_dict:
            lure_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                lure_list_msg += listing_dict[k]['message']
            report_emoji = self.bot.custom_emoji.get('lure_report', u'\U0001F4E2')
            lure_list_msg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new lure report!"
            listmsg = f"**Meowth! Here's the current {search_label} for {getattr(ctx.channel, 'mention', 'this channel')}**"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in lure_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    @_list.command(hidden=True)
    @checks.allowraidreport()
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def pokealarms(self, ctx, type="pokealarm"):
        """List the pokealarms for the channel

        Usage: !list pokealarms"""
        if type == "pokealarm":
            report_type = "pokealarm"
        else:
            report_type = "pokehuntr"
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', f"{report_type}s"]:
            await utils.safe_delete(ctx.message)
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault(report_type, {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            listmsg, pokealarm_pages = await self._pokealarmlist(ctx, report_type)
            list_messages = []
            if pokealarm_pages:
                index = 0
                for p in pokealarm_pages:
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
            self.bot.guild_dict[ctx.guild.id]['list_dict'][report_type][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict'][report_type]):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict'][report_type][channel]

    async def _pokealarmlist(self, ctx, report_type):
        pokealarm_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get(f"{report_type}_dict", {}))
        listing_dict = {}
        for pokealarmid in pokealarm_dict:
            pokealarmmsg = ""
            if pokealarm_dict[pokealarmid]['report_channel'] == ctx.message.channel.id:
                try:
                    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{ctx.channel.id}/{pokealarmid}"
                    pokealarm_expire = datetime.datetime.utcfromtimestamp(pokealarm_dict[pokealarmid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    pokealarmmsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('pokealarm_bullet', u'\U0001F539')))
                    location = pokealarm_dict[pokealarmid]['gym']
                    if pokealarm_dict[pokealarmid]['reporttype'] == "raid":
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokealarm_dict[pokealarmid]['pokemon'])
                        pokealarmmsg += f"**Boss**: {str(pokemon)} {pokemon.emoji} | **Location**: [{string.capwords(location, ' ')}](https://www.google.com/maps/search/?api=1&query={pokealarm_dict[pokealarmid]['gps']}) | **Expires**: {pokealarm_expire.strftime(_('%I:%M %p'))} | [Jump to Message]({jump_url})"
                    elif pokealarm_dict[pokealarmid]['reporttype'] == "egg":
                        pokealarmmsg += f"**Level**: {pokealarm_dict[pokealarmid]['level']} | **Location**: [{string.capwords(location, ' ')}](https://www.google.com/maps/search/?api=1&query={pokealarm_dict[pokealarmid]['gps']}) | **Hatches**: {pokealarm_expire.strftime(_('%I:%M %p'))} | [Jump to Message]({jump_url})"
                    listing_dict[pokealarmid] = {
                        "message":pokealarmmsg,
                        "expire":pokealarm_expire
                    }
                except Exception as e:
                    print("pokealarmlist", e)
                    continue
        if listing_dict:
            pokealarm_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                pokealarm_list_msg += listing_dict[k]['message']
            listmsg = _('**Meowth! Here\'s the current bot reported raids for {channel}**').format(channel=ctx.message.channel.mention)
            paginator = commands.Paginator(prefix="", suffix="")
            for line in pokealarm_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        else:
            listmsg = _("Meowth! There are no bot reported raids.")
        return listmsg, None

    @_list.command(aliases=['invasion', 'inv'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowinvasionreport()
    async def invasions(self, ctx, *, search_term="all"):
        """List the invasions for the channel

        Usage: !list invasions

        Invasion Reporting Channel Listing Options: pokemon, location, type"""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'invasions']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "invasion reports"
        if search_term != "all":
            pois = {}
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            if gym_matching_cog:
                pois = {**gym_matching_cog.get_stops(ctx.guild.id), **gym_matching_cog.get_gyms(ctx.guild.id)}
                pois = {k.lower(): v for k, v in pois.items()}
            search_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search_term)
            if search_pokemon and search_term not in self.bot.type_list and search_term not in [x.lower() for x in pois.keys()]:
                search_term = search_pokemon.name.lower()
                search_label = f"{search_term.title()} invasion reports"
            elif search_term in [x.lower() for x in pois.keys()]:
                if pois[search_term].get('alias'):
                    search_term = pois[search_term].get('alias')
                search_label = f"invasion reports at {search_term.title()}"
            elif search_term in self.bot.type_list:
                search_label = f"{search_term.title()} type invasion reports"
            else:
                search_term = "all"
        list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('invasion', {}).setdefault(ctx.channel.id, [])
        delete_list = []
        async with ctx.typing():
            for msg in list_dict:
                try:
                    msg = await ctx.channel.fetch_message(msg)
                    delete_list.append(msg)
                except:
                    pass
            await utils.safe_bulk_delete(ctx.channel, delete_list)
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
            listmsg, invasion_pages = await self._invasionlist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if invasion_pages:
                index = 0
                for p in invasion_pages:
                    list_embed.description = p
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current {search_label.title()}**", value=f"Meowth! There are no reported {search_label}. Report one with **{ctx.prefix}invasion [location], [reward or type]** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['invasion'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['invasion']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['invasion'][channel]

    async def _invasionlist(self, ctx, search_term="all"):
        invasion_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('invasion_dict', {}))
        listing_dict = {}
        search_label = "invasion reports"
        for invasionid in invasion_dict:
            condition_check = invasion_dict[invasionid]['report_channel'] == ctx.message.channel.id
            if "dm" in str(ctx.invoked_with):
                condition_check = ctx.author.id in invasion_dict[invasionid].get('dm_dict', {})
            if condition_check:
                try:
                    invasionmsg = ""
                    reward_list = []
                    pokemon_list = []
                    type_list = []
                    invasionauthor = ctx.guild.get_member(invasion_dict[invasionid]['report_author'])
                    reward = invasion_dict[invasionid]['reward']
                    reward_type = invasion_dict[invasionid].get('reward_type', None)
                    grunt_gender = invasion_dict[invasionid].get('gender', None)
                    leader = invasion_dict[invasionid].get('leader', None)
                    location = invasion_dict[invasionid]['location']
                    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{invasion_dict[invasionid]['report_channel']}/{invasionid}"
                    if invasionid in self.bot.active_invasions and len(self.bot.active_invasions[invasionid]) > 0:
                        for pokemon in self.bot.active_invasions[invasionid]:
                            shiny_str = ""
                            if pokemon and "shadow" in pokemon.shiny_available:
                                shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                            reward_list.append(f"{shiny_str}{pokemon.name.title()} {pokemon.emoji}")
                            type_list.extend(pokemon.types)
                        pokemon_list = self.bot.active_invasions[invasionid]
                    elif reward:
                        for pokemon in reward:
                            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pokemon)
                            if not pokemon:
                                continue
                            shiny_str = ""
                            if pokemon and "shadow" in pokemon.shiny_available:
                                shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                            reward_list.append(f"{shiny_str}{pokemon.name.title()} {pokemon.emoji}")
                            pokemon_list.append(pokemon)
                            type_list.extend(pokemon.types)
                        self.bot.active_invasions[invasionid] = pokemon_list
                    elif reward_type:
                        reward_list = [f"{reward_type.title()} Invasion {self.bot.config.type_id_dict[reward_type.lower()]}"]
                    if search_term != "all":
                        if pokemon_list and search_term in [x.name for x in pokemon_list]:
                            search_label = f"{search_term.title()} invasion reports"
                        elif search_term == reward_type:
                            search_label = f"{search_term.title()} invasion reports"
                        elif search_term.title() in type_list:
                            search_label = f"{search_term.title()} type invasion reports"
                        elif search_term == location.lower():
                            search_label = f"invasion reports at {search_term.title()}"
                        else:
                            continue
                    if not reward_list:
                        reward_list = ["Unknown Pokemon"]
                    invasion_expire = datetime.datetime.utcfromtimestamp(invasion_dict[invasionid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    reported_by = ""
                    if invasionauthor and not invasionauthor.bot:
                        reported_by = f" | **Reported By**: {invasionauthor.display_name}"
                    gender_str = ""
                    if leader:
                        gender_str = f" | **Leader**: {leader.title()}"
                    if grunt_gender:
                        gender_str = f" | **Gender**: {grunt_gender.title()}"
                    invasionmsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('invasion_bullet', u'\U0001F539')))
                    invasionmsg += f"**Possible Rewards**: {(', ').join(reward_list)} | **Location**: [{string.capwords(location, ' ')}]({invasion_dict[invasionid].get('url', None)}){gender_str} | **Expires**: {invasion_expire.strftime(_('%I:%M %p'))}{reported_by} | [Jump to Report]({jump_url})"
                    listing_dict[invasionid] = {
                        "message":invasionmsg,
                        "expire":invasion_expire
                    }
                except Exception as e:
                    continue
        if listing_dict:
            inv_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                inv_list_msg += listing_dict[k]['message']
            report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
            inv_list_msg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new invasion report!"
            listmsg = f"**Meowth! Here's the current {search_label} for {getattr(ctx.channel, 'mention', 'this channel')}**"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in inv_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    @_list.command(aliases=['pvps'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowpvpreport()
    async def pvp(self, ctx, search_term="all"):
        """List the pvps for the channel

        Usage: !list pvps

        PVP Reporting Channel Listing Options: league, tournament"""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'pvp']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "PVP requests"
        if search_term != "all":
            if search_term in ["great", "ultra", "master"]:
                search_label = f"{search_term} league PVP requests"
            elif search_term == "tournament":
                search_label = f"pvp tournaments"
            else:
                search_term = "all"
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
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2')
            listmsg, pvp_pages = await self._pvplist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if pvp_pages:
                index = 0
                for p in pvp_pages:
                    list_embed.description = p
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current {search_label}**", value=f"Meowth! There are no reported {search_label}. Report one with **{ctx.prefix}pvp <league> <location>** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['pvp'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['pvp']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['pvp'][channel]

    async def _pvplist(self, ctx, search_term="all"):
        pvp_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('pvp_dict', {}))
        listing_dict = {}
        search_label = "PVP requests"
        for pvpid in pvp_dict:
            if pvp_dict[pvpid]['report_channel'] == ctx.message.channel.id:
                try:
                    pvpmsg = ""
                    pvpauthor = ctx.channel.guild.get_member(pvp_dict[pvpid]['report_author'])
                    pvp_tournament = pvp_dict[pvpid].get('tournament', {})
                    pvp_type = pvp_dict[pvpid]['type']
                    location = pvp_dict[pvpid]['location']
                    if search_term != "all":
                        if search_term in ['great', 'ultra', 'master']:
                            search_label = f"{search_term} league requsts"
                        elif search_term == "tournament" and pvp_tournament:
                            search_label = f"PVP tournaments"
                        else:
                            continue
                    pvp_expire = datetime.datetime.utcfromtimestamp(pvp_dict[pvpid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    reported_by = ""
                    if pvpauthor and not pvpauthor.bot:
                        reported_by = f" | **Requested By**: {pvpauthor.display_name}"
                    pvpmsg += ('\n{emoji}').format(emoji=utils.parse_emoji(ctx.guild, self.bot.custom_emoji.get('pvp_bullet', u'\U0001F539')))
                    if pvp_tournament:
                        pvpmsg += f"**PVP Type**: {pvp_type.title()} Tournament | **Location**: [{string.capwords(location, ' ')}]({pvp_dict[pvpid].get('url', None)}) | **Tournament Size**: {pvp_tournament['size']} | **Round**: {pvp_tournament['round']}{reported_by}"
                        pass
                    else:
                        pvpmsg += f"**PVP Type**: {pvp_dict[pvpid]['type'].title()} | **Location**: [{string.capwords(location, ' ')}]({pvp_dict[pvpid].get('url', None)}) | **Available Until**: {pvp_expire.strftime(_('%I:%M %p'))}{reported_by}"
                    listing_dict[pvpid] = {
                        "message":pvpmsg,
                        "expire":pvp_expire
                    }
                except Exception as e:
                    print("pvplist", e)
                    continue
        if listing_dict:
            pvp_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                pvp_list_msg += listing_dict[k]['message']
            report_emoji = self.bot.custom_emoji.get('pvp_report', u'\U0001F4E2')
            pvp_list_msg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new PVP request!"
            listmsg = f"**Meowth! Here's the current {search_label} for {ctx.channel.mention}**"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in pvp_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    @_list.command(aliases=['wild', 'w'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allowwildreport()
    async def wilds(self, ctx, *, search_term="all"):
        """List the wilds for the channel

        Usage: !list wilds

        Wild Reporting Channel Listing Options: pokemon, location, type, level (level 30), CP (cp 1000), IV (90iv or 90)
        Add 'max' to IV, CP, level (10 iv max) to show all reports below your value, defaults to above"""
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'wilds', 'wild']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "reports"
        if search_term != "all":
            pois = {}
            search_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search_term)
            gym_matching_cog = self.bot.cogs.get('GymMatching')
            min_or_max = "min"
            if "max" in search_term:
                min_or_max = "max"
                search_term = search_term.replace('max', '').strip()
            if gym_matching_cog:
                pois = {**gym_matching_cog.get_stops(ctx.guild.id), **gym_matching_cog.get_gyms(ctx.guild.id)}
                pois = {k.lower(): v for k, v in pois.items()}
            if "level" in search_term and [x for x in search_term if x.isdigit()]:
                search_label = f"reports {'above' if min_or_max == 'min' else 'below'} Level {search_term.replace('level', '').strip()}"
                search_term = f"{search_term} {min_or_max.upper()}"
            elif "cp" in search_term and [x for x in search_term if x.isdigit()]:
                search_label = f"reports {'above' if min_or_max == 'min' else 'below'} {search_term.replace('cp', '').strip()}CP"
                search_term = f"{search_term} {min_or_max.upper()}"
            elif ("iv" in search_term or search_term.isdigit()) and [x for x in search_term if x.isdigit()]:
                search_label = f"reports {'above' if min_or_max == 'min' else 'below'} {search_term.replace('iv', '').strip()}IV"
                search_term = f"{search_term} {min_or_max.upper()}"
            elif search_term in self.bot.type_list:
                search_label = f"{search_term.title()} type reports"
            elif search_term.lower() in [x.lower() for x in pois.keys()]:
                if pois[search_term].get('alias'):
                    search_term = pois[search_term].get('alias')
                search_label = f"reports at {search_term.title()}"
            elif search_pokemon:
                search_term = search_pokemon.name.lower()
                search_label = f"{search_term.title()} reports"
            else:
                search_term = "all"
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
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
            listmsg, wild_pages = await self._wildlist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if wild_pages:
                index = 0
                for p in wild_pages:
                    list_embed.description = p
                    if index == 0:
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current Wild {search_label}**", value=f"Meowth! There are no reported wild {search_label.replace('reports', 'pokemon')}. Report one with **{ctx.prefix}wild <pokemon> <location>** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['wild'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['wild']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['wild'][channel]

    async def _wildlist(self, ctx, search_term="all"):
        wild_dict = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].get('wildreport_dict', {}))
        listing_dict = {}
        bullet_point = self.bot.custom_emoji.get('wild_bullet', u'\U0001F539')
        hundred_bullet = self.bot.custom_emoji.get('wild_hundred', u'\U0001f538')
        search_label = "reports"
        min_or_max = "min"
        if "MAX" in search_term:
            min_or_max = "max"
        for wildid in wild_dict:
            condition_check = wild_dict[wildid].get('report_channel') == ctx.channel.id
            if "dm" in str(ctx.invoked_with):
                condition_check = ctx.author.id in wild_dict[wildid].get('dm_dict')
            if condition_check:
                try:
                    wildmsg = ""
                    wildauthor = ctx.guild.get_member(wild_dict[wildid]['report_author'])
                    wild_despawn = datetime.datetime.utcfromtimestamp(wild_dict[wildid]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    timestamp = datetime.datetime.utcfromtimestamp(wild_dict[wildid]['report_time']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                    jump_url = f"https://discord.com/channels/{ctx.guild.id}/{wild_dict[wildid].get('report_channel')}/{wildid}"
                    reported_by = ""
                    if wildauthor and not wildauthor.bot:
                        reported_by = f" | **Reported By**: {wildauthor.display_name}"
                    shiny_str = ""
                    disguise_str = ""
                    wild_iv = wild_dict[wildid].get('wild_iv', {})
                    iv_check = wild_dict[wildid].get('wild_iv', {}).get('percent', None)
                    atk_check = wild_dict[wildid].get('wild_iv', {}).get('iv_atk', None)
                    def_check = wild_dict[wildid].get('wild_iv', {}).get('iv_def', None)
                    sta_check = wild_dict[wildid].get('wild_iv', {}).get('iv_sta', None)
                    cp_check = wild_dict[wildid].get('cp', None)
                    level_check = wild_dict[wildid].get('level', None)
                    weather_check = wild_dict[wildid].get('weather', None)
                    size_check = wild_dict[wildid].get('size', None)
                    gender_Check = wild_dict[wildid].get('gender', None)
                    disguise = wild_dict[wildid].get('disguise', None)
                    location = wild_dict[wildid]['location']
                    if wildid in self.bot.active_wilds:
                        pokemon = self.bot.active_wilds[wildid]
                    else:
                        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, wild_dict[wildid]['pkmn_obj'])
                        pokemon.iv = wild_iv
                        pokemon.cp = cp_check
                        pokemon.level = level_check
                        pokemon.weather = weather_check
                        pokemon.size = size_check if pokemon.size_available else None
                        pokemon.gender = gender_Check if pokemon.gender_available else None
                        self.bot.active_wilds[wildid] = pokemon
                    search_term = search_term.replace('MAX', '').replace('MIN', '').strip()
                    if search_term != "all":
                        if "level" in search_term and search_term.replace('level', '').strip().isdigit():
                            search_label = f"wild reports {'above ' if min_or_max == 'min' else 'below '}Level {search_term.replace('level', '').strip()}"
                            if not level_check:
                                continue
                            elif min_or_max == "min" and int(level_check) < int(search_term.replace('level', '').strip()):
                                continue
                            elif min_or_max == "max" and int(level_check) > int(search_term.replace('level', '').strip()):
                                continue
                        elif "cp" in search_term and search_term.replace('cp', '').strip().isdigit():
                            search_label = f"wild reports {'above ' if min_or_max == 'min' else 'below '}{search_term.replace('cp', '').strip()}CP"
                            if not cp_check:
                                continue
                            elif min_or_max == "min" and int(cp_check) < int(search_term.replace('cp', '').strip()):
                                continue
                            elif min_or_max == "max" and int(cp_check) > int(search_term.replace('cp', '').strip()):
                                continue
                        elif ("iv" in search_term or search_term.isdigit()) and search_term.replace('iv', '').strip().isdigit():
                            search_label = f"wild reports {'above ' if min_or_max == 'min' else 'below '}{search_term.replace('iv', '').strip()}IV"
                            if not iv_check and iv_check != 0:
                                continue
                            elif min_or_max == "min" and int(iv_check) < int(search_term.replace('iv', '').strip()):
                                continue
                            elif min_or_max == "max" and int(iv_check) > int(search_term.replace('iv', '').strip()):
                                continue
                        elif str(getattr(pokemon, 'name', None)).lower() == search_term:
                            search_label = f"wild {search_term.title()} reports"
                        elif search_term.title() in pokemon.types:
                            search_label = f"{search_term.title()} type wild reports"
                        elif search_term == location.lower():
                            search_label = f"reports at {search_term.title()}"
                        else:
                            continue
                    if pokemon.name.lower() == "ditto" and disguise:
                        disguise = await pkmn_class.Pokemon.async_get_pokemon(self.bot, disguise)
                        disguise.weather = weather_check
                        disguise_str = f" | **Disguise**: {disguise.name.title()} {disguise.emoji}"
                    if pokemon and "wild" in pokemon.shiny_available:
                        shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                    if iv_check and iv_check == 100:
                        wildmsg += f"\n{hundred_bullet} "
                    else:
                        wildmsg += f"\n{bullet_point} "
                    wildmsg += f"**Pokemon**: {shiny_str}{str(pokemon).title()} {pokemon.emoji}{disguise_str} | **Location**: [{string.capwords(location, ' ')}]({wild_dict[wildid].get('url', None)}) | **Despawns**: {wild_despawn.strftime(_('%I:%M %p'))}{reported_by}"
                    if (disguise and disguise.is_boosted) or (pokemon and pokemon.is_boosted):
                        wildmsg += f" | {pokemon.is_boosted or disguise.is_boosted} *({timestamp.strftime('%I:%M %p')})*"
                    if level_check:
                        wildmsg += f" | **Level**: {level_check}"
                    if cp_check:
                        wildmsg += f" | **CP**: {cp_check}"
                    if iv_check or iv_check == 0:
                        wildmsg += f" | **IV**: "
                        if any([atk_check, atk_check == 0, def_check, def_check == 0, sta_check, sta_check == 0]):
                            wildmsg += f"{atk_check if atk_check else 'X'} / {def_check if def_check else 'X'} / {sta_check if sta_check else 'X'} ({wild_dict[wildid]['wild_iv'].get('percent', iv_check)}%)"
                        else:
                            wildmsg += f"{wild_dict[wildid]['wild_iv'].get('percent', iv_check)}%"
                    wildmsg += f" | [Jump to Report]({jump_url})"
                    listing_dict[wildid] = {
                        "message":wildmsg,
                        "expire":wild_despawn
                    }
                except Exception as e:
                    print("wildlist", e)
                    continue
        if listing_dict:
            wild_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                wild_list_msg += listing_dict[k]['message']
            listmsg = f"**Meowth! Here's the current {search_label} for {getattr(ctx.channel, 'mention', 'this channel')}**"
            report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
            wild_list_msg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new wild report!"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in wild_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    # @_list.command(aliases=['nest'])
    # @commands.cooldown(1, 5, commands.BucketType.channel)
    # @checks.allownestreport()
    # async def nests(self, ctx):
    #     """List the nests for the channel
    #
    #     Usage: !list nests"""
    #     if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'nests', 'nest']:
    #         await utils.safe_delete(ctx.message)
    #     list_dict = self.bot.guild_dict[ctx.guild.id].setdefault('list_dict', {}).setdefault('nest', {}).setdefault(ctx.channel.id, [])
    #     if not ctx.prefix:
    #         prefix = self.bot._get_prefix(self.bot, ctx.message)
    #         ctx.prefix = prefix[-1]
    #     delete_list = []
    #     async with ctx.typing():
    #         for msg in list_dict:
    #             try:
    #                 msg = await ctx.channel.fetch_message(msg)
    #                 delete_list.append(msg)
    #             except:
    #                 pass
    #         await utils.safe_bulk_delete(ctx.channel, delete_list)
    #         nest_cog = self.bot.cogs.get('Nest')
    #         if not nest_cog:
    #             return
    #         list_messages = []
    #         nest_embed, nest_pages = await nest_cog.get_nest_reports(ctx)
    #         report_emoji = self.bot.custom_emoji.get('nest_report', u'\U0001F4E2')
    #         nest_pages[-1] = f"{nest_pages[-1]}\n**New Report**:\nReact with {report_emoji} to start a new nest report!"
    #         nest_embed.set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
    #         index = 0
    #         for p in nest_pages:
    #             nest_embed.description = p
    #             if index == 0:
    #                 listmsg = await ctx.channel.send(f"**Meowth!** Here's the current nests for {ctx.channel.mention}. You can see more information about a nest using **{ctx.prefix}nest info**".format(channel=ctx.channel.mention), embed=nest_embed)
    #             else:
    #                 listmsg = await ctx.channel.send(embed=nest_embed)
    #             list_messages.append(listmsg.id)
    #             index += 1
    #         await utils.add_reaction(listmsg, report_emoji)
    #         self.bot.guild_dict[ctx.guild.id]['list_dict']['nest'][ctx.channel.id] = list_messages
    #         for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['nest']):
    #             if not ctx.guild.get_channel(channel):
    #                 del self.bot.guild_dict[ctx.guild.id]['list_dict']['nest'][channel]

    @_list.command(aliases=['nest'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    @checks.allownestreport()
    async def nests(self, ctx, search_term="all"):
        if str(ctx.invoked_with).lower() in ['list', 'l', 'lists', 'nests', 'nest']:
            await utils.safe_delete(ctx.message)
        search_term = search_term.lower()
        search_label = "reports"
        if search_term != "all":
            search_pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, search_term)
            if search_term in self.bot.type_list:
                search_label = f"{search_term.title()} type reports"
            elif search_pokemon:
                search_term = search_pokemon.name.lower()
                search_label = f"{search_term.title()} reports"
            else:
                search_term = "all"
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
            if not ctx.prefix:
                prefix = self.bot._get_prefix(self.bot, ctx.message)
                ctx.prefix = prefix[-1]
            report_emoji = self.bot.custom_emoji.get('nest_report', u'\U0001F4E2')
            listmsg, nest_pages = await self._nestlist(ctx, search_term)
            list_messages = []
            list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
            if nest_pages:
                index = 0
                for p in nest_pages:
                    list_embed.description = p
                    if index == 0:
                        list_embed.title = "Click here to open the Silph Road Nest Atlas!"
                        list_embed.url = "https://thesilphroad.com/atlas"
                        listmsg = await ctx.channel.send(listmsg, embed=list_embed)
                        list_embed.title, list_embed.url = None, None
                    else:
                        listmsg = await ctx.channel.send(embed=list_embed)
                    list_messages.append(listmsg.id)
                    index += 1
                await utils.add_reaction(listmsg, report_emoji)
            else:
                report_emoji = self.bot.custom_emoji.get('nest_report', u'\U0001F4E2')
                list_embed.add_field(name=f"**No Current Nest {search_label}**", value=f"Meowth! There are no reported {search_label.replace('reports', 'pokemon')} nests. Report one with **{ctx.prefix}nest <pokemon>** or react with {report_emoji} and I can walk you through it!")
                listmsg = await ctx.channel.send(embed=list_embed)
                await utils.add_reaction(listmsg, report_emoji)
                list_messages.append(listmsg.id)
            self.bot.guild_dict[ctx.guild.id]['list_dict']['nest'][ctx.channel.id] = list_messages
            for channel in copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['list_dict']['nest']):
                if not ctx.guild.get_channel(channel):
                    del self.bot.guild_dict[ctx.guild.id]['list_dict']['nest'][channel]

    async def _nestlist(self, ctx, search_term="all"):
        nest_dict = copy.deepcopy(ctx.bot.guild_dict[ctx.guild.id].setdefault('nest_dict', {}))
        listing_dict = {}
        bullet_point = self.bot.custom_emoji.get('nest_bullet', u'\U0001F539')
        search_label = "reports"
        empty_nests = []
        for channel_id in nest_dict:
            nest_list = nest_dict[channel_id].get('list', [])
            channel = self.bot.get_channel(channel_id)
            for nest in nest_list:
                if not nest_dict[channel.id][nest].get('reports'):
                    empty_nests.append(nest.title())
                for report in nest_dict[channel.id][nest]['reports']:
                    condition_check = channel.id == ctx.channel.id
                    if "dm" in str(ctx.invoked_with):
                        condition_check = ctx.author.id in nest_dict[channel.id][nest]['reports'][report].get('dm_dict', {})
                    if condition_check:
                        try:
                            nest_msg = ""
                            nest_coordinates = nest_dict[channel.id][nest]['location']
                            nest_name = str(nest)
                            nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_coordinates)}"
                            nest_author = ctx.guild.get_member(nest_dict[channel.id][nest]['reports'][report]['report_author'])
                            nest_despawn = datetime.datetime.utcfromtimestamp(nest_dict[channel.id][nest]['reports'][report]['exp']) + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0))
                            jump_url = f"https://discord.com/channels/{ctx.guild.id}/{nest_dict[channel.id][nest]['reports'][report].get('report_channel')}/{report}"
                            reported_by = ""
                            if nest_author and not nest_author.bot:
                                reported_by = f" | **Reported By**: {nest_author.display_name}"
                            if report in self.bot.active_nests:
                                pokemon = self.bot.active_nests[report]
                            else:
                                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, nest_dict[channel.id][nest]['reports'][report]['pokemon'])
                                self.bot.active_nests[report] = pokemon
                            if search_term != "all":
                                if str(getattr(pokemon, 'name', None)).lower() == search_term:
                                    search_label = f"{search_term.title()} nest reports"
                                elif search_term.title() in pokemon.types:
                                    search_label = f"{search_term.title()} type nest reports"
                                else:
                                    continue
                            shiny_str = ""
                            if pokemon and "wild" in pokemon.shiny_available:
                                shiny_str = self.bot.custom_emoji.get('shiny_chance', u'\U00002728') + " "
                            nest_msg += f"\n{bullet_point} **Pokemon**: {shiny_str}{str(pokemon).title()} {pokemon.emoji} | **Nest**: [{string.capwords(nest_name, ' ')}]({nest_url}) | **Migration**: {nest_despawn.strftime(_('%B %d at %I:%M %p (%H:%M)'))}{reported_by}"
                            nest_msg += f" | [Jump to Report]({jump_url})"
                            listing_dict[report] = {
                                "message":nest_msg,
                                "expire":nest_despawn
                            }
                        except Exception as e:
                            print("nestlist", e)
                            continue
        if listing_dict or (empty_nests and "dm" not in str(ctx.invoked_with)):
            nest_list_msg = ""
            for (k, v) in sorted(listing_dict.items(), key=lambda item: item[1]['expire']):
                nest_list_msg += listing_dict[k]['message']
            listmsg = f"**Meowth!** Here's the current {search_label} for {getattr(ctx.channel, 'mention', 'this channel')}. You can see more information about a nest using **{ctx.prefix}nest info**"
            report_emoji = self.bot.custom_emoji.get('nest_report', u'\U0001F4E2')
            if empty_nests and "dm" not in str(ctx.invoked_with):
                nest_list_msg += f"\n\n**Empty Nests**:\n{(', ').join(empty_nests)}"
            nest_list_msg += f"\n\n**New Report:**\nReact with {report_emoji} to start a new nest report!"
            paginator = commands.Paginator(prefix="", suffix="")
            for line in nest_list_msg.splitlines():
                paginator.add_line(line.rstrip().replace('`', '\u200b`'))
            return listmsg, paginator.pages
        return None, None

    @_list.command(aliases=['dm'])
    @commands.cooldown(1, 5, commands.BucketType.channel)
    async def dms(self, ctx):
        listing_dict = {}
        list_msg = ""
        for guild in self.bot.guilds:
            ctx.guild = guild
            listing_dict[guild.name] = {}
            for report_dict in self.bot.report_dicts + self.bot.channel_report_dicts:
                report_type = report_dict.replace('channel_dict', '').replace('_dict', '').replace('report', '')
                if report_type == "quest":
                    report_emoji = self.bot.custom_emoji.get('research_report', u'\U0001F4E2')
                    listmsg, listpages = await self._researchlist(ctx)
                    if listpages:
                        listing_dict[guild.name]['research'] = ('\n\n'+('\n').join(listpages)).replace('**Pokemon Encounters**', '').replace('**Stardust**', '').replace('**Rare Candy**', '').replace('**Berries**', '').replace('**Potions**', '').replace('**Revives**', '').replace('**Poke Balls**', '').replace('**Other Rewards**', '').replace('\n\n', '').replace(f"**New Report:**\nReact with {report_emoji} to start a new research report!", "")+'\n'
                elif report_type == "wild":
                    report_emoji = self.bot.custom_emoji.get('wild_report', u'\U0001F4E2')
                    listmsg, listpages = await self._wildlist(ctx)
                    if listpages:
                        listing_dict[guild.name][report_type] = ('\n\n'+('\n').join(listpages)).replace('\n\n', '').replace(f"**New Report:**\nReact with {report_emoji} to start a new wild report!", "")+'\n'
                elif report_type == "lure":
                    report_emoji = self.bot.custom_emoji.get('lure_report', u'\U0001F4E2')
                    listmsg, listpages = await self._lurelist(ctx)
                    if listpages:
                        listing_dict[guild.name][report_type] = ('\n\n'+('\n').join(listpages)).replace('\n\n', '').replace(f"**New Report:**\nReact with {report_emoji} to start a new lure report!", "")+'\n'
                elif report_type == "invasion":
                    report_emoji = self.bot.custom_emoji.get('invasion_report', u'\U0001F4E2')
                    listmsg, listpages = await self._invasionlist(ctx)
                    if listpages:
                        listing_dict[guild.name][report_type] = ('\n\n'+('\n').join(listpages)).replace('\n\n', '').replace(f"**New Report:**\nReact with {report_emoji} to start a new invasion report!", "")+'\n'
                elif report_type == "raid":
                    report_emoji = self.bot.custom_emoji.get('raid_report', u'\U0001F4E2')
                    listmsg, __ = await self._raidlist(ctx)
                    if listmsg:
                        listing_dict[guild.name][report_type] = listmsg.replace(f"\n\n**New Report:**\nReact with {report_emoji} to start a new raid report!", "").replace("**Raid Eggs:**\n", "").replace("**Raids:**\n", "").replace("**EX Raids:**\n", "")
                elif report_type == "nest":
                    report_emoji = self.bot.custom_emoji.get('nest_report', u'\U0001F4E2')
                    listmsg, listpages = await self._nestlist(ctx)
                    if listmsg:
                        listing_dict[guild.name][report_type] = ('\n\n'+('\n').join(listpages)).replace('\n\n', '').replace(f"**New Report:**\nReact with {report_emoji} to start a new nest report!", "")+'\n'
        for guild in self.bot.guilds:
            if not listing_dict[guild.name]:
                continue
            list_msg += f"**{guild.name}**\n\n"
            for report_type in listing_dict[guild.name]:
                list_msg += f"__{report_type.title()}__\n"
                list_msg += listing_dict[guild.name][report_type]
        paginator = commands.Paginator(prefix="", suffix="")
        for line in list_msg.splitlines():
            paginator.add_line(line.rstrip().replace('`', '\u200b`'))
        list_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url=f"https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/emoji/unicode_spiralnotepad.png?cache=1")
        if paginator.pages:
            index = 0
            for p in paginator.pages:
                list_embed.description = p
                if index == 0:
                    listmsg = await ctx.channel.send(f"Meowth! Here are your active alerts.", embed=list_embed)
                else:
                    listmsg = await ctx.channel.send(embed=list_embed)
                index += 1
        else:
            list_embed.add_field(name=f"**No Active Alerts**", value=f"Meowth! You have no active alerts.")
            listmsg = await ctx.channel.send(embed=list_embed, delete_after=30)

def setup(bot):
    bot.add_cog(Listing(bot))

def teardown(bot):
    bot.remove_cog(Listing)

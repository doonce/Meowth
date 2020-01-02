import asyncio
import copy
import re
import time
import datetime
import dateparser
import textwrap
import logging

import discord
from discord.ext import commands

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Trainers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["mystic", "valor", "instinct", "harmony"])
    @checks.allowteam()
    async def team(self, ctx, *, team=None):
        """Set your team role.

        Usage: !team [team name]
        This command can be used only once. Moderators will have to manually change teams."""
        guild = ctx.guild
        team_assigned = ""
        error = False
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset']))
        guild_roles = self.bot.guild_dict[guild.id]['configure_dict']['team'].setdefault('team_roles', {"mystic":None, "valor":None, "instinct":None, "harmony":None})
        team_colors = {"mystic":discord.Colour.blue(), "valor":discord.Colour.red(), "instinct":discord.Colour.gold(), "harmony":discord.Colour.default()}
        if not guild_roles or guild_roles == {}:
            guild_roles = {"mystic":None, "valor":None, "instinct":None, "harmony":None}
        for team_name in guild_roles:
            if not guild_roles[team_name]:
                try:
                    team_role = await guild.create_role(name=f"Meowth{team_name.capitalize()}", hoist=False, mentionable=True, colour=team_colors[team_name])
                    guild_roles[team_name] = team_role.id
                except discord.errors.HTTPException:
                    return await ctx.channel.send(_('Maximum guild roles reached. Contact an admin.'), delete_after=10)
                except (discord.errors.Forbidden, discord.errors.InvalidArgument):
                    return await ctx.channel.send(_('I can\'t create roles!. Contact an admin.'), delete_after=10)
        team_roles = {k: ctx.guild.get_role(v) for (k, v) in guild_roles.items()}
        for team_name, role in team_roles.items():
            if role in ctx.author.roles:
                team_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict[team_name])
                team_assigned = f"{team_name.title()} {team_emoji}"
            if role.position > guild.me.top_role.position:
                return await ctx.channel.send(f"Meowth! My role is ranked lower than the team roles. Contact an admin.", delete_after=10)
        harmony = team_roles.get('harmony', None)
        if team_assigned and harmony not in ctx.author.roles:
            return await ctx.channel.send(f"Meowth! You are already in Team {team_assigned}! If you are trying to change your team using a Team Medallion, please contact a moderator.", delete_after=10)
        if ctx.invoked_with == "mystic" or ctx.invoked_with == "valor" or ctx.invoked_with == "instinct" or ctx.invoked_with == "harmony":
            team = ctx.invoked_with.lower()
        if not team:
            team_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/teams/harmony.png?cache=1')
            team_embed.set_footer(text=_('Assigning @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
            while True:
                async with ctx.typing():
                    def check(reply):
                        if reply.author is not guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                            return True
                        else:
                            return False
                    team_embed.add_field(name=_('**Team Assignment**'), value=_("Meowth! I'll help you assign your team!\n\nReply with **mystic, valor, instinct, or harmony**. You can reply with **cancel** to stop anytime."), inline=False)
                    team_wait = await ctx.send(embed=team_embed)
                    try:
                        team_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        team_msg = None
                    await utils.safe_delete(team_wait)
                    if not team_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(team_msg)
                    if team_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif not any([team_msg.clean_content.lower() == "mystic", team_msg.clean_content.lower() == "blue", team_msg.clean_content.lower() == "valor", team_msg.clean_content.lower() == "red", team_msg.clean_content.lower() == "instinct", team_msg.clean_content.lower() == "yellow", team_msg.clean_content.lower() == "harmony"]):
                        error = _("entered an invalid team. Choose from mystic, valor, instinct, harmony")
                        break
                    elif team_msg:
                        team = team_msg.clean_content.lower()
                        team = team.replace("blue", "mystic").replace("red", "valor").replace("yellow", "instinct")
                break
        if error:
            team_embed.clear_fields()
            team_embed.add_field(name=_('**Team Assignment Cancelled**'), value=_("Meowth! Your team assignment has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            return await ctx.send(embed=team_embed, delete_after=10)
        team_split = team.lower().split()
        entered_team = team_split[0]
        entered_team = ''.join([i for i in entered_team if i.isalpha()])
        role = None
        if entered_team in team_roles.keys():
            role = team_roles[entered_team]
        else:
            return await ctx.channel.send(_('Meowth! "{entered_team}" isn\'t a valid team! Try {available_teams}').format(entered_team=entered_team, available_teams=(' or ').join([f"{ctx.prefix}team {x}" for x in guild_roles.keys()])), delete_after=10)
        if role and (role.name.lower() == 'harmony') and (harmony in ctx.author.roles):
            return await ctx.channel.send(_('Meowth! You are already in Team Harmony!'), delete_after=10)
        elif role == None:
            return await ctx.channel.send(_('Meowth! The "{entered_team}" role isn\'t configured on this server! Contact an admin!').format(entered_team=entered_team), delete_after=10)
        else:
            try:
                if harmony and (harmony in ctx.author.roles):
                    await ctx.author.remove_roles(harmony)
                await ctx.author.add_roles(role)
                await ctx.channel.send(_('Meowth! Added {member} to Team {team_name}! {team_emoji}').format(member=ctx.author.mention, team_name=entered_team.capitalize(), team_emoji=utils.parse_emoji(ctx.guild, self.bot.config.team_dict[entered_team])))
            except discord.Forbidden:
                await ctx.channel.send(_("Meowth! I can't add roles!"), delete_after=10)

    @commands.command(aliases=['whois'])
    @checks.guildchannel()
    async def profile(self, ctx, *, member=""):
        """Displays a member's social and reporting profile.

        Usage:!profile [member]
        Searches in-game names, trainerodes, etc. to find other trainers."""
        converter = commands.MemberConverter()
        msg = ""
        if member:
            try:
                member = await converter.convert(ctx, member)
            except:
                member_found = False
                for trainer in self.bot.guild_dict[ctx.guild.id]['trainers']:
                    search_list = []
                    user = ctx.guild.get_member(trainer)
                    if not user:
                        continue
                    search_list.append(user.name.lower())
                    search_list.append(user.display_name.lower())
                    search_list.append(str(user.id))
                    pbid = str(self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('pokebattlerid', "")).lower()
                    if pbid:
                        search_list.append(pbid)
                    trainercode = self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('trainercode', "").replace(" ", "").lower()
                    if trainercode:
                        search_list.append(trainercode)
                    ign = self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('ign', "")
                    if ign:
                        ign = ign.split(',')
                        ign = [x.strip().lower() for x in ign]
                        search_list = search_list + ign
                    silphid = self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('silphid', "").lower()
                    if silphid:
                        search_list.append(silphid)
                    if member.lower() in search_list:
                        member = trainer
                        member_found = True
                        break
                if member_found:
                    member = ctx.guild.get_member(member)
                else:
                    msg = f"{ctx.author.mention}, I couldn't find your search, but here is your profile:"
                    member = None
        if not member:
            member = ctx.message.author
        trainers = self.bot.guild_dict[ctx.guild.id]['trainers']
        silph = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('silphid', None)
        if silph:
            silph = f"[Traveler Card](https://sil.ph/{silph.lower()})"
        else:
            silph = f"Set with {ctx.prefix}silph"
        trainercode = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('trainercode', None)
        if not trainercode:
            trainercode = f"Set with {ctx.prefix}trainercode"
        pokebattler = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('pokebattlerid', None)
        if not pokebattler:
            pokebattler = f"Set with {ctx.prefix}pokebattler"
        trade_list = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('trade_list', None)
        trade_message = None
        if trade_list:
            for k,v in trade_list.items():
                trade_channel = self.bot.get_channel(k)
                try:
                    trade_message = await trade_channel.fetch_message(v)
                    trade_message = trade_message.jump_url
                except:
                    trade_message = None
        want_list = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('want_list', None)
        want_message = None
        if want_list:
            for k,v in want_list.items():
                want_channel = self.bot.get_channel(k)
                try:
                    want_message = await want_channel.fetch_message(v)
                    want_message = want_message.jump_url
                except:
                    want_message = None
        ign = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('ign', None)
        pvp_info = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('pvp', {})
        raids = trainers.get(member.id, {}).get('reports', {}).get('raid', 0)
        eggs = trainers.get(member.id, {}).get('reports', {}).get('egg', 0)
        exraids = trainers.get(member.id, {}).get('reports', {}).get('ex', 0)
        wilds = trainers.get(member.id, {}).get('reports', {}).get('wild', 0)
        research = trainers.get(member.id, {}).get('reports', {}).get('research', 0)
        nests = trainers.get(member.id, {}).get('reports', {}).get('nest', 0)
        lures = trainers.get(member.id, {}).get('reports', {}).get('lure', 0)
        roles = [x.mention for x in sorted(member.roles, reverse=True) if ctx.guild.id != x.id]
        embed = discord.Embed(title=_("{member}\'s Trainer Profile").format(member=member.display_name), colour=member.colour)
        embed.set_thumbnail(url=member.avatar_url)
        status_emoji = ""
        if str(member.web_status) == "online":
            status_emoji = "\U0001F310"
        if (member.desktop_status) == "online":
            status_emoji = "\U0001F4BB"
        if member.is_on_mobile():
            status_emoji = "\U0001F4F1"
        embed.set_footer(text=f"User Registered: {member.created_at.strftime(_('%b %d, %Y %I:%M %p'))} | Status: {str(member.status).title()} {status_emoji}")
        if "set with" not in str(silph).lower() or member == ctx.author:
            embed.add_field(name=_("Silph Road"), value=silph, inline=True)
        if "set with" not in str(pokebattler).lower() or member == ctx.author:
            embed.add_field(name=_("Pokebattler"), value=pokebattler, inline=True)
        if "set with" not in str(trainercode).lower() or member == ctx.author:
            embed.add_field(name=_("Trainer Code"), value=trainercode, inline=True)
        embed.add_field(name=_("Member Since"), value=f"{member.joined_at.strftime(_('%b %d, %Y %I:%M %p'))}", inline=True)
        if ign:
            embed.add_field(name="In-Game Name(s)", value=ign)
        field_value = ""
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled'] and raids:
            field_value += _("Raid: **{raids}** | ").format(raids=raids)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled'] and eggs:
            field_value += _("Egg: **{eggs}** | ").format(eggs=eggs)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['exraid']['enabled'] and exraids:
            field_value += _("EX: **{exraids}** | ").format(exraids=exraids)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled'] and wilds:
            field_value += _("Wild: **{wilds}** | ").format(wilds=wilds)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['research']['enabled'] and research:
            field_value += _("Quest: **{research}** | ").format(research=research)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled'] and nests:
            field_value += _("Nest: **{nest}** | ").format(nest=nests)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled'] and lures:
            field_value += _("Lure: **{lure}** | ").format(lure=lures)
        if field_value:
            embed.add_field(name=_("Reports"), value=field_value[:-3], inline=False)
        if want_message and self.bot.guild_dict[ctx.guild.id]['configure_dict']['want']['enabled'] and (want_channel.overwrites_for(ctx.guild.default_role).read_messages or want_channel.overwrites_for(ctx.guild.default_role).read_messages == None):
            embed.add_field(name=_("Want List"), value=f"[Click here]({want_message}) to view most recent want list in {want_channel.mention}.")
        if trade_message and (trade_channel.overwrites_for(ctx.guild.default_role).read_messages or trade_channel.overwrites_for(ctx.guild.default_role).read_messages == None):
            embed.add_field(name="Active Trades", value=f"[Click here]({trade_message}) to view active trades in {trade_channel.mention}.")
        if any([pvp_info.get('champion'), pvp_info.get('elite'), pvp_info.get('leader'), pvp_info.get('badges'), pvp_info.get('record')]):
            champ_emoji = self.bot.config.custom_emoji.get('pvp_champ', u'\U0001F451')
            elite_emoji = self.bot.config.custom_emoji.get('pvp_elite', u'\U0001F3C6')
            pvp_value = []
            if pvp_info.get('champion'):
                pvp_value.append(f"{champ_emoji} {(', ').join([x.title() for x in pvp_info['champion']])} League Champion {champ_emoji}")
            if pvp_info.get('elite'):
                pvp_value.append(f"{elite_emoji} Elite Four {elite_emoji}")
            if pvp_info.get('leader'):
                pvp_value.append(f"Gym Leader: {('').join([utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[x]) for x in pvp_info['leader']])}")
            if pvp_info.get('badges'):
                pvp_value.append(f"Badges: {('').join([utils.parse_emoji(ctx.guild, self.bot.config.type_id_dict[x]) for x in pvp_info['badges']])}")
            if pvp_info.get('record'):
                pvp_value.append(f"Record: {pvp_info['record'].get('win', 0)}W - {pvp_info['record'].get('loss', 0)}L")
            if pvp_value:
                embed.add_field(name=_("PVP League Info"), value=(' | ').join(pvp_value), inline=False)
        if roles:
            embed.add_field(name=_("Roles"), value=f"{(' ').join(roles)[:2000]}", inline=False)

        await ctx.send(msg, embed=embed)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @checks.guildchannel()
    async def leaderboard(self, ctx, type="total", range="1"):
        """Displays the top ten reporters of a server.

        Usage: !leaderboard [type] [page]
        Accepted types: raid, egg, exraid, wild, research, nest, lure, invasion
        Page: 1 = 1 through 10, 2 = 11 through 20, etc."""
        trainers = copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['trainers'])
        leaderboard = []
        field_value = ""
        typelist = ["total", "raid", "exraid", "wild", "research", "egg", "nest", "lure", "invasion"]
        type = type.lower()
        if type.isdigit():
            range = type
            type = "total"
        if not range.isdigit():
            range = "1"
        range = int(range) * 10
        begin_range = int(range) - 10
        rank = int(range) - 9
        if type not in typelist:
            await ctx.send(_("Leaderboard type not supported. Please select from: **{typelist}**").format(typelist = ", ".join(typelist)), delete_after=10)
            return
        for trainer in trainers.keys():
            user = ctx.guild.get_member(trainer)
            raid = trainers[trainer].get('reports', {}).get('raid', 0)
            wild = trainers[trainer].get('reports', {}).get('wild', 0)
            exraid = trainers[trainer].get('reports', {}).get('ex', 0)
            egg = trainers[trainer].get('reports', {}).get('egg', 0)
            research = trainers[trainer].get('reports', {}).get('research', 0)
            nest = trainers[trainer].get('reports', {}).get('nest', 0)
            lure = trainers[trainer].get('reports', {}).get('lure', 0)
            invasion = trainers[trainer].get('reports', {}).get('invasion', 0)
            total_reports = sum(trainers[trainer].get('reports', {0:0}).values())
            trainer_stats = {'trainer':trainer, 'total':total_reports, 'raid':raid, 'wild':wild, 'research':research, 'exraid':exraid, 'egg':egg, 'nest':nest, 'lure':lure, 'invasion':invasion}
            if trainer_stats[type] > 0 and user:
                leaderboard.append(trainer_stats)
        leaderboard = sorted(leaderboard, key= lambda x: x[type], reverse=True)[begin_range:int(range)]
        embed = discord.Embed(colour=ctx.guild.me.colour)
        embed.set_author(name=_("Reporting Leaderboard ({type})").format(type=type.title()), icon_url=self.bot.user.avatar_url)
        for trainer in leaderboard:
            user = ctx.guild.get_member(trainer['trainer'])
            if user:
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled']:
                    field_value += f"Raid: **{trainer['raid']+trainer['egg']+trainer['exraid']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled']:
                    field_value += f"Wild: **{trainer['wild']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['research']['enabled']:
                    field_value += f"Research: **{trainer['research']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
                    field_value += f"Nest: **{trainer['nest']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['lure']['enabled']:
                    field_value += f"Lure: **{trainer['lure']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['invasion']['enabled']:
                    field_value += f"Invasion: **{trainer['invasion']}** | "
                embed.add_field(name=f"{rank}. {user.display_name} - {type.title()}: **{trainer[type]}**", value=field_value[:-3], inline=False)
                field_value = ""
                rank += 1
        if len(embed.fields) == 0:
            embed.add_field(name=_("No Reports"), value=_("Nobody has made a report or this report type is disabled."))
        await ctx.send(embed=embed)

    @leaderboard.command(name='reset')
    @commands.has_permissions(manage_guild=True)
    async def reset(self, ctx, *, user=None, type=None):
        """Resets Leaderboard

        Usage: !leaderboard reset [user] [type]"""
        guild = ctx.guild
        trainers = self.bot.guild_dict[guild.id]['trainers']
        tgt_string = ""
        tgt_trainer = None
        type_list = ["raid", "egg", "ex", "wild", "research", "nest", "lure", "invasion", "trade", "pvp"]
        if user:
            converter = commands.MemberConverter()
            for argument in user.split():
                try:
                    tgt_trainer = await converter.convert(ctx, argument)
                    tgt_string = tgt_trainer.display_name
                except:
                    tgt_trainer = None
                    tgt_string = _("every user")
                if tgt_trainer:
                    user = user.replace(argument, "").strip()
                    break
            for argument in user.split():
                if "raid" in argument.lower():
                    type = "raid"
                    break
                elif "egg" in argument.lower():
                    type = "egg"
                    break
                elif "ex" in argument.lower():
                    type = "ex"
                    break
                elif "wild" in argument.lower():
                    type = "wild"
                    break
                elif "res" in argument.lower():
                    type = "research"
                    break
                elif "nest" in argument.lower():
                    type = "nest"
                    break
                elif "lure" in argument.lower():
                    type = "lure"
                    break
        if not type:
            type = "total_reports"
        if not tgt_string:
            tgt_string = _("every user")
        msg = _("Are you sure you want to reset the **{type}** report stats for **{target}**?").format(type=type.replace("_", " ").title(), target=tgt_string)
        question = await ctx.channel.send(msg)
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
        except TypeError:
            timeout = True
        await utils.safe_delete(question)
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
            pass
        else:
            return
        for trainer in trainers:
            if tgt_trainer:
                trainer = tgt_trainer.id
            if type == "total_reports":
                for item in type_list:
                    try:
                        del trainers[trainer]['reports'][item]
                    except KeyError:
                        continue
            else:
                try:
                    del trainers[trainer]['reports'][type]
                except KeyError:
                    continue
            if tgt_trainer:
                await ctx.send(_("{trainer}'s report stats have been cleared!").format(trainer=tgt_trainer.display_name), delete_after=10)
                return
        await ctx.send("This server's report stats have been reset!", delete_after=10)

    @commands.command()
    @checks.guildchannel()
    async def pokebattler(self, ctx, *, pbid: str = ""):
        """Links a server member to a PokeBattler ID.

        To clear your setting, use !pokebattler clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].get('trainers', {})
        author = trainers.get(ctx.author.id, {})
        if author.get('pokebattlerid') and (pbid.lower() == "clear" or pbid.lower() == "reset"):
            await ctx.send(_('Your PokeBattler ID has been cleared!'), delete_after=10)
            try:
                del self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['pokebattlerid']
            except:
                pass
            return
        elif author.get('pokebattlerid') and pbid:
            question = await ctx.channel.send(f"Your PokeBattler ID is already set to **{author.get('pokebattlerid')}**. Do you want to change it to **{pbid}**?")
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                return await ctx.channel.send(f"{ctx.author.display_name}\'s PokeBattler ID is: **{author.get('pokebattlerid')}**")
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                pass
            else:
                return
        elif author.get('pokebattlerid'):
            return await ctx.channel.send(f"{ctx.author.display_name}\'s PokeBattler ID is: **{author.get('pokebattlerid')}**")
        elif not pbid or not pbid.isdigit():
            return await ctx.error(f"Please enter your PokeBattler ID. Try again when ready.")
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['pokebattlerid'] = int(pbid)
        await ctx.send(f"{ctx.author.mention}, your Pokebattler ID has been set to **{pbid}**!", delete_after=10)
        await utils.safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

    @commands.command()
    @checks.guildchannel()
    async def trainercode(self, ctx, *, trainercode: str = ""):
        """Links a server member to a Pokemon Go Trainer Code.

        To clear your setting, use !trainercode clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].get('trainers', {})
        author = trainers.get(ctx.author.id, {})
        if author.get('trainercode') and (trainercode.lower() == "clear" or trainercode.lower() == "reset"):
            await ctx.send(_('Your trainer code has been cleared!'), delete_after=10)
            try:
                del self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trainercode']
            except:
                pass
            return
        elif author.get('trainercode') and trainercode:
            question = await ctx.channel.send(f"Your trainer code is already set to **{author.get('trainercode')}**. Do you want to change it to **{trainercode}**?")
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                return await ctx.channel.send(f"{ctx.author.display_name}\'s trainer code is: **{author.get('trainercode')}**")
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                pass
            else:
                return
        elif author.get('trainercode'):
            return await ctx.channel.send(f"{ctx.author.display_name}\'s trainer code is: **{author.get('trainercode')}**")
        elif not trainercode:
            return await ctx.error(f"Please enter your trainer code. Try again when ready.")
        trainercode = trainercode.replace(" ", "")
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trainercode'] = trainercode[:50]
        await ctx.send(f"{ctx.author.mention}, your trainer code has been set to **{trainercode}**!", delete_after=10)
        await utils.safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

    @commands.command()
    @checks.guildchannel()
    async def ign(self, ctx, *, ign: str = ""):
        """Links a server member to a comma separated list of Pokemon Go in-game name(s).

        To clear your setting, use !ign clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].get('trainers', {})
        author = trainers.get(ctx.author.id, {})
        if author.get('ign') and (ign.lower() == "clear" or ign.lower() == "reset"):
            await ctx.send(_('Your in-game name(s) have been cleared!'), delete_after=10)
            try:
                del self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['ign']
            except:
                pass
            return
        elif author.get('ign') and ign:
            question = await ctx.channel.send(f"Your in-game name(s) are already set to **{author.get('ign')}**. Do you want to change it to **{ign}**?")
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                return await ctx.channel.send(f"{ctx.author.display_name}\'s in-game name(s) are: **{author.get('ign')}**")
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                pass
            else:
                return
        elif author.get('ign'):
            return await ctx.channel.send(f"{ctx.author.display_name}\'s in-game name(s) are: **{author.get('ign')}**")
        elif not ign:
            return await ctx.error(f"Please enter your in-game name. Try again when ready.")
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['ign'] = ign[:300]
        await ctx.send(f"{ctx.author.mention}, your in-game name(s) have been set to **{ign}**!", delete_after=10)
        await utils.safe_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

def setup(bot):
    bot.add_cog(Trainers(bot))

def teardown(bot):
    bot.remove_cog(Trainers)

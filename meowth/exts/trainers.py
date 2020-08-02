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

    @commands.group(aliases=["mystic", "valor", "instinct", "harmony"], case_insensitive=True, invoke_without_command=True)
    @checks.allowteam()
    async def team(self, ctx, *, team=None):
        """Set your team role.

        Usage: !team [team name]
        This command can be used only once. Moderators will have to manually change teams."""
        guild = ctx.guild
        team_assigned = ""
        error = False
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
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
                    team_embed.add_field(name=_('**Team Assignment**'), value=_("Meowth! I'll help you assign your team!\n\nReply with **mystic, valor, instinct, or harmony**. You can Reply with **cancel** to stop anytime."), inline=False)
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
                        team_embed.clear_fields()
                        team_embed.add_field(name=f"**Team Assignment Error**", value=f"Meowth! You entered an invalid team! Choose from mystic, valor, instinct, harmony.", inline=False)
                        await ctx.send(embed=team_embed, delete_after=10)
                        continue
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

    @team.command()
    @checks.is_mod()
    @checks.allowteam()
    async def change(self, ctx, *, user=""):
        if not user:
            member = ctx.author
        else:
            converter = commands.MemberConverter()
            try:
                member = await converter.convert(ctx, user)
            except:
                return
        error = False
        timestamp = (ctx.message.created_at + datetime.timedelta(hours=self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('settings', {}).get('offset', 0)))
        guild_roles = self.bot.guild_dict[ctx.guild.id]['configure_dict']['team'].setdefault('team_roles', {"mystic":None, "valor":None, "instinct":None, "harmony":None})
        team_colors = {"mystic":discord.Colour.blue(), "valor":discord.Colour.red(), "instinct":discord.Colour.gold(), "harmony":discord.Colour.default()}
        team_embed = discord.Embed(colour=ctx.guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/teams/harmony.png?cache=1')
        team_embed.set_footer(text=_('Assigning @{author} - {timestamp}').format(author=ctx.author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=ctx.author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                team_embed.clear_fields()
                def check(reply):
                    if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                        return True
                    else:
                        return False
                team_embed.add_field(name=_('**Team Assignment**'), value=f"Meowth! I'll help you change {member.mention}'s team!\n\nReply with **mystic, valor, instinct, or harmony**. You can Reply with **cancel** to stop anytime.", inline=False)
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
                    team_embed.clear_fields()
                    team_embed.add_field(name=f"**Team Assignment Error**", value=f"Meowth! You entered an invalid team! Choose from mystic, valor, instinct, harmony.", inline=False)
                    await ctx.send(embed=team_embed, delete_after=10)
                    continue
                elif team_msg:
                    team = team_msg.clean_content.lower()
                    team = team.replace("blue", "mystic").replace("red", "valor").replace("yellow", "instinct")
            break
        if error:
            team_embed.clear_fields()
            team_embed.add_field(name=_('**Team Assignment Cancelled**'), value=_("Meowth! Team assignment has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            return await ctx.send(embed=team_embed, delete_after=10)
        old_team = ""
        team_roles = {k: ctx.guild.get_role(v) for (k, v) in guild_roles.items()}
        for team_name, role in team_roles.items():
            if role in member.roles:
                team_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict[team_name])
                old_team = f"{team_name.title()} {team_emoji}"
                await member.remove_roles(role)
        team_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict[team])
        new_team = f"{team.title()} {team_emoji}"
        await member.add_roles(team_roles[team])
        return await ctx.send(f"I changed **{member.display_name}** from **{'No ' if not old_team else ''}Team {old_team}** to **Team {new_team}**!")

    @commands.group(aliases=['whois'], case_insensitive=True, invoke_without_command=True)
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
                for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
                    search_list = []
                    user = ctx.guild.get_member(trainer)
                    if not user:
                        continue
                    search_list.append(user.name.lower())
                    search_list.append(user.display_name.lower())
                    search_list.append(str(user.id))
                    pbid = str(self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(trainer, {}).get('pokebattlerid', "")).lower()
                    if pbid:
                        search_list.append(pbid)
                    silphid = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})[trainer].get('silphid', "").lower()
                    if silphid:
                        search_list.append(silphid)
                    trainercode = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})[trainer].get('trainercode', "").replace(" ", "").lower()
                    if trainercode:
                        search_list.append(trainercode)
                    ign = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})[trainer].get('ign', "")
                    if ign:
                        ign = ign.split(',')
                        ign = [x.strip().lower() for x in ign]
                        search_list = search_list + ign
                    for account in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {}):
                        search_list.append(self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('ign').lower())
                        search_list.append(self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('trainercode'))
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
        trainers = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})
        trade_list = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('trade_list', None)
        trade_message = None
        if trade_list:
            for k,v in trade_list.items():
                trade_channel = self.bot.get_channel(k)
                try:
                    trade_message = await trade_channel.fetch_message(v)
                    trade_message = trade_message.jump_url
                except:
                    trade_message = None
        want_list = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('want_list', None)
        want_message = None
        if want_list:
            for k,v in want_list.items():
                want_channel = self.bot.get_channel(k)
                try:
                    want_message = await want_channel.fetch_message(v)
                    want_message = want_message.jump_url
                except:
                    want_message = None
        bulletpoint = self.bot.custom_emoji.get('bullet', u'\U0001F539')
        embed = discord.Embed(title=f"{member.display_name}'s Trainer Profile", colour=member.colour)
        embed.set_thumbnail(url=member.avatar_url)
        silph = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('silphid', None)
        trainercode = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('trainercode', None)
        pokebattler = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('pokebattlerid', None)
        ign = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('ign', None)
        team_emoji_dict = {"mystic": utils.parse_emoji(ctx.guild, self.bot.config.team_dict['mystic']), "valor": utils.parse_emoji(ctx.guild, self.bot.config.team_dict['valor']), "instinct": utils.parse_emoji(ctx.guild, self.bot.config.team_dict['instinct']), "harmony": utils.parse_emoji(ctx.guild, self.bot.config.team_dict['harmony'])}
        user_team = ""
        for team_role in self.bot.guild_dict[ctx.guild.id]['configure_dict']['team']['team_roles']:
            for role in member.roles:
                if role.id == self.bot.guild_dict[ctx.guild.id]['configure_dict']['team']['team_roles'][team_role]:
                    user_team = team_role
                    break
        field_value = []
        if ign:
            field_value.append(f"**Name**: {ign}")
        elif member == ctx.author:
            field_value.append(f"**Name**: Set with {ctx.prefix}ign")
        if trainercode:
            field_value.append(f"**Trainercode**: {trainercode}")
        elif member == ctx.author:
            field_value.append(f"**Trainercode**: Set with {ctx.prefix}trainercode")
        if silph:
            field_value.append(f"**Silph**: [Traveler Card](https://sil.ph/{silph.lower()})")
        elif member == ctx.author:
            field_value.append(f"**Silph**: Set with {ctx.prefix}silph")
        if pokebattler:
            field_value.append(f"**PokeBattler**: [Profile](https://pokebattler.com/profiles/{pokebattler})")
        elif member == ctx.author:
            field_value.append(f"**PokeBattler**: Set with {ctx.prefix}pokebattler")
        if user_team:
            field_value.append(f"**Team**: {team_emoji_dict[user_team]}")
        elif member == ctx.author:
            field_value.append(f"**Team**: Set with {ctx.prefix}team")
        if field_value:
            embed.add_field(name=f"Game Account", value=f"{bulletpoint}{(' | ').join(field_value)}")
        user_accounts = self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('accounts')
        if user_accounts:
            field_value = ""
            for account in user_accounts:
                account_name = self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['accounts'][account].get('ign')
                account_code = self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['accounts'][account].get('trainercode')
                account_team = self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['accounts'][account].get('team')
                field_value += f"{bulletpoint} **Name**: {account_name} | **Trainercode**: {account_code} | **Team**: {team_emoji_dict[account_team]}\n"
            embed.add_field(name=f"Other Game Accounts", value=field_value, inline=False)
        field_value = ""
        raids = trainers.get(member.id, {}).get('reports', {}).get('raid', 0)
        eggs = trainers.get(member.id, {}).get('reports', {}).get('egg', 0)
        exraids = trainers.get(member.id, {}).get('reports', {}).get('ex', 0)
        wilds = trainers.get(member.id, {}).get('reports', {}).get('wild', 0)
        research = trainers.get(member.id, {}).get('reports', {}).get('research', 0)
        nests = trainers.get(member.id, {}).get('reports', {}).get('nest', 0)
        lures = trainers.get(member.id, {}).get('reports', {}).get('lure', 0)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('raid', {}).get('enabled', False) and raids:
            field_value += _("Raid: **{raids}** | ").format(raids=raids)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('raid', {}).get('enabled', False) and eggs:
            field_value += _("Egg: **{eggs}** | ").format(eggs=eggs)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['exraid'].get('enabled', False) and exraids:
            field_value += _("EX: **{exraids}** | ").format(exraids=exraids)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('wild', {}).get('enabled', False) and wilds:
            field_value += _("Wild: **{wilds}** | ").format(wilds=wilds)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('research', {}).get('enabled', False) and research:
            field_value += _("Quest: **{research}** | ").format(research=research)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('nest', {}).get('enabled', False) and nests:
            field_value += _("Nest: **{nest}** | ").format(nest=nests)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('nest', {}).get('enabled', False) and lures:
            field_value += _("Lure: **{lure}** | ").format(lure=lures)
        if field_value:
            embed.add_field(name=_("Reports"), value=field_value[:-3], inline=False)
        if want_message and self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('want', {}).get('enabled', False) and (want_channel.overwrites_for(ctx.guild.default_role).read_messages or want_channel.overwrites_for(ctx.guild.default_role).read_messages == None):
            embed.add_field(name=_("Want List"), value=f"[Click here]({want_message}) to view most recent want list in {want_channel.mention}.")
        if trade_message and (trade_channel.overwrites_for(ctx.guild.default_role).read_messages or trade_channel.overwrites_for(ctx.guild.default_role).read_messages == None):
            embed.add_field(name="Active Trades", value=f"[Click here]({trade_message}) to view active trades in {trade_channel.mention}.")
        pvp_info = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(member.id, {}).get('pvp', {})
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
        roles = [x.mention for x in sorted(member.roles, reverse=True) if ctx.guild.id != x.id]
        if roles:
            embed.add_field(name=_("Roles"), value=f"{(' ').join(roles)[:2000]}", inline=False)
        status_emoji = ""
        if str(member.web_status) == "online":
            status_emoji = "\U0001F310"
        if (member.desktop_status) == "online":
            status_emoji = "\U0001F4BB"
        if member.is_on_mobile():
            status_emoji = "\U0001F4F1"
        embed.set_footer(text=f"Registered: {member.created_at.strftime(_('%b %d, %Y %I:%M %p'))} | Joined: {member.joined_at.strftime(_('%b %d, %Y %I:%M %p'))} | Status: {str(member.status).title()} {status_emoji}")
        await ctx.send(msg, embed=embed)

    @profile.command(name="add")
    async def profile_add(self, ctx):
        embed = discord.Embed(colour=ctx.author.colour)
        embed.set_thumbnail(url=ctx.author.avatar_url)
        new_account = {
            "ign":None,
            "trainercode":None,
            "team":None
        }
        error = ""
        search_dict = {}
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('ign')] = trainer
            search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('trainercode')] = trainer
            for account in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {}):
                search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('ign').lower()] = trainer
                search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('trainercode')] = trainer
        user_accounts = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(ctx.author.id, {}).get('accounts', {})
        if len(user_accounts) == 5:
            embed.add_field(name=f"**Add Account Error**", value=f"Meowth! You are only allowed five alternate accounts. To add another account, remove one first with **{ctx.prefix}profile remove**")
            return await ctx.send(embed=embed)
        while True:
            async with ctx.typing():
                embed.add_field(name=f"**Add Alternate Account**", value=f"Meowth! I'll help you add an alternate account to your profile. First, what is the **account name**? Reply with **cancel** to stop anytime.", inline=False)
                value_wait = await ctx.send(embed=embed)
                def check(reply):
                    if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                        return True
                    else:
                        return False
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif value_msg.clean_content.lower() in search_dict:
                    dupe_account = ctx.guild.get_member(search_dict[value_msg.clean_content.lower()])
                    error = f"that account name is already claimed by {dupe_account.mention}. Contact a moderator if there is a dispute**"
                    break
                else:
                    new_account['ign'] = value_msg.clean_content
                    embed.clear_fields()
                    embed.add_field(name=f"**Add Alternate Account**", value=f"Great! Next, what is the **trainercode** for {new_account['ign']}? Reply with **cancel** to stop anytime.")
                    value_wait = await ctx.send(embed=embed)
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif not [x for x in value_msg.clean_content.lower() if x.isdigit()] or len(value_msg.clean_content.lower().replace(" ", '')) != 12:
                    error = f"entered an invalid trainer code"
                    break
                elif value_msg.clean_content.lower().replace(" ", '') in search_dict:
                    dupe_account = ctx.guild.get_member(search_dict[value_msg.clean_content.lower()])
                    error = f"that trainer code is already claimed by {dupe_account.mention}. Contact a moderator if there is a dispute**"
                    break
                else:
                    new_account['trainercode'] = value_msg.clean_content.replace(' ', '')
                    embed.clear_fields()
                    embed.add_field(name=f"**Add Alternate Account**", value=f"Great! Next, what **team** is {new_account['ign']} (code: {new_account['trainercode']}) on? Choose from mystic, valor, instinct, harmony. Reply with **cancel** to stop anytime.")
                    value_wait = await ctx.send(embed=embed)
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif value_msg.clean_content.lower() not in ["mystic", "valor", "instinct", "harmony"]:
                    error = f"entered an invalid team"
                    break
                else:
                    new_account['team'] = value_msg.clean_content.lower()
                    break
        if not error:
            bulletpoint = self.bot.custom_emoji.get('bullet', u'\U0001F539')
            team_emoji = utils.parse_emoji(ctx.guild, self.bot.config.team_dict[new_account['team']])
            add_account = {new_account['ign']: {"ign":new_account['ign'], "trainercode":new_account['trainercode'], "team":new_account['team']}}
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['accounts'] = {**user_accounts, **add_account}
            embed.clear_fields()
            embed.add_field(name=f"**Successfully Added Account**", value=f"{bulletpoint} **Name**: {new_account['ign']} | **Trainercode**: {new_account['trainercode']} | **Team**: {team_emoji}")
            await ctx.send(embed=embed, delete_after=120)
        else:
            embed.clear_fields()
            embed.add_field(name=_('**Add Account Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await ctx.send(embed=embed, delete_after=60)

    @profile.command(name="remove")
    async def profile_remove(self, ctx):
        embed = discord.Embed(colour=ctx.author.colour)
        embed.set_thumbnail(url=ctx.author.avatar_url)
        error = ""
        user_accounts = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(ctx.author.id, {}).get('accounts', {})
        account_names = list(user_accounts.keys())
        lowercase_names = [x.lower() for x in account_names]
        while True:
            async with ctx.typing():
                embed.add_field(name=f"**Remove Alternate Account**", value=f"Meowth! I'll help you Remove an alternate account to your profile. What is the **account name** you'd like to remove from the choices below? Reply with **cancel** to stop anytime.\n\n{(', ').join(account_names)}", inline=False)
                value_wait = await ctx.send(embed=embed)
                def check(reply):
                    if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                        return True
                    else:
                        return False
                try:
                    value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                except asyncio.TimeoutError:
                    value_msg = None
                await utils.safe_delete(value_wait)
                if not value_msg:
                    error = _("took too long to respond")
                    break
                else:
                    await utils.safe_delete(value_msg)
                if value_msg.clean_content.lower() == "cancel":
                    error = _("cancelled the report")
                    break
                elif value_msg.clean_content.lower().strip() not in lowercase_names:
                    error = f"entered an invalid account"
                    break
                else:
                    delete_account = lowercase_names.index(value_msg.clean_content.lower().strip())
                    delete_account = account_names[delete_account]
                    del user_accounts[delete_account]
                    embed.clear_fields()
                    break
        if not error:
            embed.clear_fields()
            embed.add_field(name=f"**Successfully Removed Account**", value=f"Removed **{delete_account}** from your profile.")
            await ctx.send(embed=embed, delete_after=120)
        else:
            embed.clear_fields()
            embed.add_field(name=_('**Add Account Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=embed, delete_after=60)

    @checks.is_mod()
    @profile.command(name="reset")
    async def profile_reset(self, ctx, member=""):
        embed = discord.Embed(colour=ctx.author.colour)
        embed.set_thumbnail(url=ctx.author.avatar_url)
        error = ""
        converter = commands.MemberConverter()
        msg = ""
        if member:
            try:
                member = await converter.convert(ctx, member)
            except:
                return await ctx.send(f"I couldn't find that member. Try again with a @mention or a case-sensitive username.", delete_after=10)
        else:
            while True:
                async with ctx.typing():
                    embed.add_field(name=f"**Reset Trainer Profile**", value=f"Meowth! I'll help you reset a trainer profile. What is the **account name** or **@mention** of the user profile you'd like to reset? This will remove all in-game names and trainercodes set to this member. Reply with **cancel** to stop anytime.", inline=False)
                    value_wait = await ctx.send(embed=embed)
                    def check(reply):
                        if reply.author is not ctx.guild.me and reply.channel.id == ctx.channel.id and reply.author == ctx.author:
                            return True
                        else:
                            return False
                    try:
                        value_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        value_msg = None
                    await utils.safe_delete(value_wait)
                    if not value_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(value_msg)
                    if value_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    else:
                        try:
                            member = await converter.convert(ctx, value_msg.content)
                            break
                        except Exception as e:
                            print(e)
                            return await ctx.send(f"I couldn't find that member. Try again with an @mention or a case-sensitive username.", delete_after=10)
        if member:
            question = await ctx.channel.send(f"Are you sure you'd like to reset the in-game names and trainercodes for @{member.display_name}?")
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
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['ign'] = ''
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['trainercode'] = ''
            self.bot.guild_dict[ctx.guild.id]['trainers'][member.id]['accounts'] = {}
        if not error:
            embed.clear_fields()
            embed.add_field(name=f"**Successfully Reset Profile**", value=f"Removed the in-game names and trainercodes of **{member.mention}**.")
            await ctx.send(embed=embed, delete_after=120)
        else:
            embed.clear_fields()
            embed.add_field(name=_('**Profile Reset Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=embed, delete_after=60)

    @profile.command(name="edit")
    async def profile_edit(self, ctx):
        """Displays options for editing profile"""
        embed = discord.Embed(title=f"Profile Commands", colour=ctx.author.colour)
        embed.set_thumbnail(url=ctx.author.avatar_url)
        embed.add_field(name=f"{ctx.prefix}trainercode [code]", value=f"Set trainer code of your main account to [code].", inline=False)
        embed.add_field(name=f"{ctx.prefix}trainercode [reset]", value=f"Remove trainer code.", inline=False)
        embed.add_field(name=f"{ctx.prefix}ign [name]", value=f"Set in-game name of your main account to [name].", inline=False)
        embed.add_field(name=f"{ctx.prefix}ign [reset]", value=f"Remove in-game name from profile.", inline=False)
        embed.add_field(name=f"{ctx.prefix}silph [silphid]", value=f"Set silph ID of your main account to [silphid]", inline=False)
        embed.add_field(name=f"{ctx.prefix}silph [reset]", value=f"Remove Silph ID from profile", inline=False)
        embed.add_field(name=f"{ctx.prefix}pokebattler [pokebattlerid]", value=f"Set PokeBattler ID of your main account to [pokebattlerid]", inline=False)
        embed.add_field(name=f"{ctx.prefix}pokebattler [reset]", value=f"Removes PokeBattler ID from profile.", inline=False)
        embed.add_field(name=f"{ctx.prefix}profile add", value=f"Add an alternate account to your profile.", inline=False)
        embed.add_field(name=f"{ctx.prefix}profile remove", value=f"Remove alternate account from your profile.", inline=False)
        await ctx.send(embed=embed)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    async def leaderboard(self, ctx, type="total", range="1"):
        """Displays the top ten reporters of a server.

        Usage: !leaderboard [type] [page]
        Accepted types: raid, egg, exraid, wild, research, nest, lure, invasion
        Page: 1 = 1 through 10, 2 = 11 through 20, etc."""
        trainers = copy.deepcopy(self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}))
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
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('raid', {}).get('enabled', False):
                    field_value += f"Raid: **{trainer['raid']+trainer['egg']+trainer['exraid']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('wild', {}).get('enabled', False):
                    field_value += f"Wild: **{trainer['wild']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('research', {}).get('enabled', False):
                    field_value += f"Research: **{trainer['research']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('nest', {}).get('enabled', False):
                    field_value += f"Nest: **{trainer['nest']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('lure', {}).get('enabled', False):
                    field_value += f"Lure: **{trainer['lure']}** | "
                if self.bot.guild_dict[ctx.guild.id]['configure_dict'].get('invasion', {}).get('enabled', False):
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
        trainers = self.bot.guild_dict[guild.id].setdefault('trainers', {})
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
    async def pokebattler(self, ctx, *, pbid: str = ""):
        """Links a server member to a PokeBattler ID.

        To clear your setting, use !pokebattler clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})
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
            return await ctx.channel.send(f"{ctx.author.display_name}\'s PokeBattler ID is:", embed=discord.Embed(description=f"{author.get('pokebattlerid')}"))
        elif not pbid or not pbid.isdigit():
            return await ctx.error(f"Please enter your PokeBattler ID. Try again when ready.")
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['pokebattlerid'] = int(pbid)
        await ctx.send(f"{ctx.author.mention}, your Pokebattler ID has been set to **{pbid}**!", delete_after=10)
        await utils.add_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

    @commands.command()
    async def trainercode(self, ctx, *, trainercode: str = ""):
        """Links a server member to a Pokemon Go Trainer Code.

        To clear your setting, use !trainercode clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].get('trainers', {})
        author = trainers.setdefault(ctx.author.id, {})
        search_dict = {}
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('trainercode', '').replace(' ', '').lower()] = trainer
            for account in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {}):
                search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('trainercode').replace(' ', '').lower()] = trainer
        if author.get('trainercode') and (trainercode.lower() == "clear" or trainercode.lower() == "reset"):
            await ctx.send(_('Your trainer code has been cleared!'), delete_after=30)
            try:
                del self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trainercode']
            except:
                pass
            return
        elif author.get('trainercode') and trainercode:
            if [x for x in trainercode if x.isdigit()]:
                if len(trainercode.replace(" ", "")) != 12:
                    return await ctx.channel.send(f"You entered an invalid trainer code. Trainer codes contain 12 digits.", delete_after=30)
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
            else:
                for trainer in ctx.bot.guild_dict[ctx.guild.id]['trainers']:
                    search_dict = {}
                    user = ctx.guild.get_member(trainer)
                    if not user:
                        continue
                    user_code = self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {})[trainer].get('trainercode', "").replace(" ", "").lower()
                    if user_code:
                        search_dict[user.name.lower()] = {"name":user.name, "code":user_code, "member":user.name}
                    for account in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {}):
                        user_code = self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('trainercode')
                        if user_code:
                            search_dict[account.lower()] = {"name":account, "code":user_code, "member":user.name}
                    if trainercode.lower() in search_dict:
                        return await ctx.channel.send(f"{search_dict[trainercode.lower()]['name']}{' (@'+search_dict[trainercode.lower()]['member']+')' if search_dict[trainercode.lower()]['member'] != search_dict[trainercode.lower()]['name'] else ''}'s trainer code is:", embed=discord.Embed(description=f"{search_dict[trainercode.lower()]['code']}"))
                return await ctx.send(f"I couldn't find that account", delete_after=30)
        elif author.get('trainercode'):
            return await ctx.channel.send(f"{ctx.author.display_name}\'s trainer code is:", embed=discord.Embed(description=f"{author.get('trainercode')}"))
        elif not trainercode:
            return await ctx.error(f"Please enter your trainer code. Try again when ready.")
        trainercode = trainercode.replace(" ", "")
        if trainercode.lower() in search_dict.keys():
            dupe_account = ctx.guild.get_member(search_dict[trainercode.lower()])
            if dupe_account != ctx.author:
                error_embed = discord.Embed(description=f"That trainer code is already claimed by {dupe_account.mention}. Contact a moderator if there is a dispute.")
            else:
                error_embed = discord.Embed(description=f"Your trainer code is already set to **{trainercode}**. Clear it with **{ctx.prefix}trainercode clear**")
            error_embed.set_author(name=f"Trainer Code Error", icon_url="https://i.imgur.com/juhq2uJ.png")
            return await ctx.send(embed=error_embed)
        if len(trainercode.replace(" ", "")) != 12:
            return await ctx.channel.send(f"You entered an invalid trainer code. Trainer codes contain 12 digits.", delete_after=30)
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['trainercode'] = trainercode[:50]
        await ctx.send(f"{ctx.author.mention}, your trainer code has been set to **{trainercode}**!", delete_after=30)
        await utils.add_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

    @commands.command()
    async def ign(self, ctx, *, ign: str = ""):
        """Links a server member to a comma separated list of Pokemon Go in-game name(s).

        To clear your setting, use !ign clear."""
        trainers = self.bot.guild_dict[ctx.guild.id].get('trainers', {})
        author = trainers.setdefault(ctx.author.id, {})
        search_dict = {}
        for trainer in self.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}):
            search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('ign', '').lower()] = trainer
            for account in self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {}):
                search_dict[self.bot.guild_dict[ctx.guild.id]['trainers'][trainer].get('accounts', {})[account].get('ign', '').lower()] = trainer
        if author.get('ign') and (ign.lower() == "clear" or ign.lower() == "reset"):
            await ctx.send(_('Your in-game name has been cleared!'), delete_after=30)
            try:
                del self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['ign']
            except:
                pass
            return
        elif author.get('ign') and ign:
            question = await ctx.channel.send(f"Your in-game name is already set to **{author.get('ign')}**. Do you want to change it to **{ign}**?")
            try:
                timeout = False
                res, reactuser = await utils.ask(self.bot, question, ctx.message.author.id)
            except TypeError:
                timeout = True
            await utils.safe_delete(question)
            if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', u'\U0000274e'):
                return await ctx.channel.send(f"{ctx.author.display_name}\'s in-game name is: **{author.get('ign')}**")
            elif res.emoji == self.bot.custom_emoji.get('answer_yes', u'\U00002705'):
                pass
            else:
                return
        elif author.get('ign'):
            return await ctx.channel.send(f"{ctx.author.display_name}\'s in-game name(s) are:", embed=discord.Embed(description=f"{author.get('ign')}"))
        elif not ign:
            return await ctx.error(f"Please enter your in-game name. Try again when ready.")
        if ign.lower() in search_dict.keys():
            dupe_account = ctx.guild.get_member(search_dict[ign.lower()])
            if dupe_account != ctx.author:
                error_embed = discord.Embed(description=f"That account name is already claimed by {dupe_account.mention}. Contact a moderator if there is a dispute.")
            else:
                error_embed = discord.Embed(description=f"Your account name is already set to **{ign}**. Clear it with **{ctx.prefix}ign clear**.")
            error_embed.set_author(name=f"Account Name Error", icon_url="https://i.imgur.com/juhq2uJ.png")
            return await ctx.send(embed=error_embed)
        self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['ign'] = ign[:300]
        await ctx.send(f"{ctx.author.mention}, your in-game name has been set to **{ign}**!", delete_after=30)
        await utils.add_reaction(ctx.message, self.bot.custom_emoji.get('command_done', u'\U00002611'))

def setup(bot):
    bot.add_cog(Trainers(bot))

def teardown(bot):
    bot.remove_cog(Trainers)

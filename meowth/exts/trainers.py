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

    @commands.command()
    @checks.allowteam()
    async def team(self, ctx, *, team):
        """Set your team role.

        Usage: !team <team name>
        The team roles have to be created manually beforehand by the server administrator."""
        guild = ctx.guild
        toprole = guild.me.top_role.name
        position = guild.me.top_role.position
        guild_roles = self.bot.guild_dict[guild.id]['configure_dict']['team']['team_roles']
        team_roles = {k: discord.utils.get(ctx.guild.roles, id=v) for (k, v) in guild_roles.items()}
        high_roles = []
        team_colors = [discord.Colour.blue(), discord.Colour.red(), discord.Colour.gold(), discord.Colour.default()]
        team_msg = _(' or ').join(['**!team {0}**'.format(team) for team in guild_roles.keys()])
        index = 0
        for teamrole in copy.deepcopy(guild_roles).keys():
            role = team_roles.get(teamrole, None)
            if not role:
                rolename = f"Meowth{teamrole.capitalize()}"
                try:
                    role = await guild.create_role(name=rolename, hoist=False, mentionable=True, colour=team_colors[index])
                except discord.errors.HTTPException:
                    await ctx.message.channel.send(_('Maximum guild roles reached.'), delete_after=10)
                    return
                except (discord.errors.Forbidden, discord.errors.InvalidArgument):
                    await ctx.message.channel.send(_('I can\'t create roles!.'), delete_after=10)
                    return
                self.bot.guild_dict[guild.id]['configure_dict']['team']['team_roles'][teamrole] = role.id
                team_roles[teamrole] = role
            if role.position > position:
                high_roles.append(role.name)
            index += 1
        if high_roles:
            await ctx.channel.send(_('Meowth! My roles are ranked lower than the following team roles: **{higher_roles_list}**\nPlease get an admin to move my roles above them!').format(higher_roles_list=', '.join(high_roles)), delete_after=10)
            return
        harmony = team_roles.get('harmony', None)
        team_split = team.lower().split()
        entered_team = team_split[0]
        entered_team = ''.join([i for i in entered_team if i.isalpha()])
        role = None
        if entered_team in team_roles.keys():
            role = team_roles[entered_team]
        else:
            await ctx.channel.send(_('Meowth! "{entered_team}" isn\'t a valid team! Try {available_teams}').format(entered_team=entered_team, available_teams=team_msg), delete_after=10)
            return
        for team in team_roles.values():
            if (team in ctx.author.roles) and (harmony not in ctx.author.roles):
                await ctx.channel.send(_('Meowth! You already have a team role!'), delete_after=10)
                return
        if role and (role.name.lower() == 'harmony') and (harmony in ctx.author.roles):
            await ctx.channel.send(_('Meowth! You are already in Team Harmony!'), delete_after=10)
        elif role == None:
            await ctx.channel.send(_('Meowth! The "{entered_team}" role isn\'t configured on this server! Contact an admin!').format(entered_team=entered_team), delete_after=10)
        else:
            try:
                if harmony and (harmony in ctx.author.roles):
                    await ctx.author.remove_roles(harmony)
                await ctx.author.add_roles(role)
                await ctx.channel.send(_('Meowth! Added {member} to Team {team_name}! {team_emoji}').format(member=ctx.author.mention, team_name=entered_team.capitalize(), team_emoji=utils.parse_emoji(ctx.guild, self.bot.config['team_dict'][entered_team])))
            except discord.Forbidden:
                await ctx.channel.send(_("Meowth! I can't add roles!"), delete_after=10)

    @commands.command()
    async def trainercode(self, ctx, user: discord.Member = None):
        """Displays a user's trainer code."""
        if not user:
            user = ctx.message.author
        trainercode = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(user.id, {}).get('trainercode', None)
        if trainercode:
            await ctx.channel.send(f"{user.display_name}\'s trainer code is: **{trainercode}**")
        else:
            await ctx.channel.send(f"{user.display_name} has not set a trainer code. Set it with **!set trainercode <code>**")

    @commands.command()
    async def profile(self, ctx, member: discord.Member = None):
        """Displays a member's social and reporting profile.

        Usage:!profile [member]"""
        if not member:
            member = ctx.message.author
        trainers = self.bot.guild_dict[ctx.guild.id]['trainers']
        silph = self.bot.guild_dict[ctx.guild.id]['trainers'].setdefault(member.id, {}).get('silphid', None)
        if silph:
            card = _("Traveler Card")
            silph = f"[{card}](https://sil.ph/{silph.lower()})"
        field_value = ""
        raids = trainers.get(member.id, {}).get('raid_reports', 0)
        eggs = trainers.get(member.id, {}).get('egg_reports', 0)
        exraids = trainers.get(member.id, {}).get('ex_reports', 0)
        wilds = trainers.get(member.id, {}).get('wild_reports', 0)
        research = trainers.get(member.id, {}).get('research_reports', 0)
        nests = trainers.get(member.id, {}).get('nest_reports', 0)
        lures = trainers.get(member.id, {}).get('lure_reports', 0)
        wants = trainers.get(member.id, {}).get('alerts', {}).get('wants', [])
        wants = sorted(wants)
        wants = [utils.get_name(self.bot, x).title() for x in wants]
        roles = [x.mention for x in sorted(member.roles, reverse=True) if ctx.guild.id != x.id]
        embed = discord.Embed(title=_("{member}\'s Trainer Profile").format(member=member.display_name), colour=member.colour)
        embed.set_thumbnail(url=member.avatar_url)
        embed.set_footer(text=f"User Registered: {member.created_at.strftime(_('%b %d, %Y %I:%M %p'))} | Status: {str(member.status).title()}")
        embed.add_field(name=_("Silph Road"), value=f"{silph}", inline=True)
        embed.add_field(name=_("Pokebattler"), value=f"{self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('pokebattlerid', None)}", inline=True)
        embed.add_field(name=_("Trainer Code"), value=f"{self.bot.guild_dict[ctx.guild.id]['trainers'].get(member.id, {}).get('trainercode', None)}", inline=True)
        embed.add_field(name=_("Member Since"), value=f"{member.joined_at.strftime(_('%b %d, %Y %I:%M %p'))}", inline=True)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled']:
            field_value += _("Raid: **{raids}** | Egg: **{eggs}**").format(raids=raids, eggs=eggs)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['exraid']['enabled']:
            field_value += _(" | EX: **{exraids}**").format(exraids=exraids)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled']:
            field_value += _(" | Wild: **{wilds}**").format(wilds=wilds)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['research']['enabled']:
            field_value += _(" | Research: **{research}**").format(research=research)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
            field_value += _(" | Nest: **{nest}**").format(nest=nests)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
            field_value += _(" | Lure: **{lure}**").format(lure=lures)
        embed.add_field(name=_("Reports"), value=field_value[:-3], inline=False)
        if self.bot.guild_dict[ctx.guild.id]['configure_dict']['want']['enabled'] and wants:
            embed.add_field(name=_("Want List"), value=f"{(', ').join(wants)[:2000]}", inline=False)
        if roles:
            embed.add_field(name=_("Roles"), value=f"{(' ').join(roles)[:2000]}", inline=False)

        await ctx.send(embed=embed)

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @checks.guildchannel()
    async def leaderboard(self, ctx, type="total", range="1"):
        """Displays the top ten reporters of a server.

        Usage: !leaderboard [type] [page]
        Accepted types: raids, eggs, exraids, wilds, research, nest, lure
        Page: 1 = 1 through 10, 2 = 11 through 20, etc."""
        trainers = copy.deepcopy(self.bot.guild_dict[ctx.guild.id]['trainers'])
        leaderboard = []
        field_value = ""
        typelist = ["total", "raid", "exraid", "wild", "research", "eggs", "nest", "lure"]
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
            raid = trainers[trainer].get('raid_reports', 0)
            wild = trainers[trainer].get('wild_reports', 0)
            exraid = trainers[trainer].get('ex_reports', 0)
            egg = trainers[trainer].get('egg_reports', 0)
            research = trainers[trainer].get('research_reports', 0)
            nest = trainers[trainer].get('nest_reports', 0)
            lure = trainers[trainer].get('lure_reports', 0)
            total_reports = raid + wild + exraid + egg + research + nest + lure
            trainer_stats = {'trainer':trainer, 'total':total_reports, 'raid':raid, 'wild':wild, 'research':research, 'exraid':exraid, 'egg':egg, 'nest':nest, 'lure':lure}
            if trainer_stats[type] > 0 and user:
                leaderboard.append(trainer_stats)
        leaderboard = sorted(leaderboard, key= lambda x: x[type], reverse=True)[begin_range:int(range)]
        embed = discord.Embed(colour=ctx.guild.me.colour)
        embed.set_author(name=_("Reporting Leaderboard ({type})").format(type=type.title()), icon_url=self.bot.user.avatar_url)
        for trainer in leaderboard:
            user = ctx.guild.get_member(trainer['trainer'])
            if user:
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['raid']['enabled']:
                    field_value += _("Raid: **{raids}** | Egg: **{eggs}**").format(raids=trainer['raid'], eggs=trainer['egg'])
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['exraid']['enabled']:
                    field_value += _(" | EX: **{exraids}**").format(exraids=trainer['exraid'])
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['wild']['enabled']:
                    field_value += _(" | Wild: **{wilds}**").format(wilds=trainer['wild'])
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['research']['enabled']:
                    field_value += _(" | Quest: **{research}**").format(research=trainer['research'])
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
                    field_value += _(" | Nest: **{nest}**").format(nest=trainer['nest'])
                if self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest']['enabled']:
                    field_value += _(" | Lure: **{lure}**").format(lure=trainer['lure'])
                embed.add_field(name=f"{rank}. {user.display_name} - {type.title()}: **{trainer[type]}**", value=field_value, inline=False)
                field_value = ""
                rank += 1
        if len(embed.fields) == 0:
            embed.add_field(name=_("No Reports"), value=_("Nobody has made a report or this report type is disabled."))
        await ctx.send(embed=embed)

    @leaderboard.command(name='reset')
    @commands.has_permissions(manage_guild=True)
    async def reset(self, ctx, *, user=None, type=None):
        guild = ctx.guild
        trainers = self.bot.guild_dict[guild.id]['trainers']
        tgt_string = ""
        tgt_trainer = None
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
                    type = "raid_reports"
                    break
                elif "egg" in argument.lower():
                    type = "egg_reports"
                    break
                elif "ex" in argument.lower():
                    type = "ex_reports"
                    break
                elif "wild" in argument.lower():
                    type = "wild_reports"
                    break
                elif "res" in argument.lower():
                    type = "research_reports"
                    break
                elif "nest" in argument.lower():
                    type = "nest_reports"
                    break
                elif "lure" in argument.lower():
                    type = "lure_reports"
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
        if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
            return
        elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
            pass
        else:
            return
        for trainer in trainers:
            if tgt_trainer:
                trainer = tgt_trainer.id
            if type == "total_reports":
                trainers[trainer]['raid_reports'] = 0
                trainers[trainer]['wild_reports'] = 0
                trainers[trainer]['ex_reports'] = 0
                trainers[trainer]['egg_reports'] = 0
                trainers[trainer]['research_reports'] = 0
                trainers[trainer]['nest_reports'] = 0
                trainers[trainer]['lure_reports'] = 0
            else:
                trainers[trainer][type] = 0
            if tgt_trainer:
                await ctx.send(_("{trainer}'s report stats have been cleared!").format(trainer=tgt_trainer.display_name), delete_after=10)
                return
        await ctx.send("This server's report stats have been reset!", delete_after=10)

def setup(bot):
    bot.add_cog(Trainers(bot))

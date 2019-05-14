import asyncio
import copy
import re
import time
import datetime
import dateparser
import logging

import discord
from discord.ext import commands, tasks

from meowth import checks
from meowth.exts import pokemon as pkmn_class
from meowth.exts import utilities as utils

logger = logging.getLogger("meowth")

class Nest(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.nest_cleanup.start()

    def cog_unload(self):
        self.nest_cleanup.cancel()

    # nest_dict:{
    #     nestrepotchannel_id: {
    #         list:[],
    #         nest:{
    #             location: nest_Details,
    #             reports:{
    #                 nestrepormsg.id: {
    #                     'exp':time.time() + despawn,
    #                     'expedit': "delete",
    #                     'reportmessage':message.id,
    #                     'reportchannel':message.channel.id,
    #                     'reportauthor':message.author.id,
    #                     'dm_dict': dm_dict,
    #                     'location':nest_details,
    #                     'url':nest_link,
    #                     'pokemon':pokemon
    #                 }
    #             }
    #         }
    #     }
    # }

    @tasks.loop(seconds=0)
    async def nest_cleanup(self, loop=True):
        while True:
            logger.info('------ BEGIN ------')
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            migration_list = []
            count = 0
            for guildid in guilddict_temp.keys():
                nest_dict = guilddict_temp[guildid].setdefault('nest_dict', {})
                utcnow = datetime.datetime.utcnow()
                migration_utc = guilddict_temp[guildid]['configure_dict']['nest']['migration']
                new_migration = False
                if utcnow > migration_utc:
                    new_migration = migration_utc + datetime.timedelta(days=14)
                    migration_local = new_migration + datetime.timedelta(hours=self.bot.guild_dict[guildid]['configure_dict']['settings']['offset'])
                    self.bot.guild_dict[guildid]['configure_dict']['nest']['migration'] = new_migration
                to_migration = migration_utc.timestamp() - utcnow.timestamp()
                migration_list.append(to_migration)
                for channel in nest_dict:
                    report_channel = self.bot.get_channel(channel)
                    if not report_channel:
                        del self.bot.guild_dict[guildid]['nest_dict'][channel]
                        continue
                    for nest in nest_dict[channel]:
                        if nest == 'list':
                            continue
                        for report in nest_dict[channel][nest]['reports']:
                            if nest_dict[channel][nest]['reports'][report].get('exp', 0) <= time.time():
                                try:
                                    report_message = await report_channel.fetch_message(report)
                                    if new_migration and nest_dict[channel][nest]['reports'][report]['reporttime'] > migration_utc:
                                        self.bot.guild_dict[guildid]['nest_dict'][channel][nest]['reports'][report]['exp'] = new_migration.replace(tzinfo=datetime.timezone.utc).timestamp()
                                        self.bot.loop.create_task(self.edit_nest_reports(report_message, migration_local, nest_dict[channel][nest]['reports'][report]['dm_dict']))
                                        count += 1
                                        continue
                                    await utils.safe_delete(report_message)
                                except:
                                    pass
                                try:
                                    self.bot.loop.create_task(utils.expire_dm_reports(self.bot, nest_dict[channel][nest]['reports'][report].get('dm_dict', {})))
                                    del self.bot.guild_dict[guildid]['nest_dict'][channel][nest]['reports'][report]
                                except:
                                    pass
            if not migration_list:
                migration_list = [600]
            logger.info(f"------ END - {count} Nests Cleaned - Waiting {min(migration_list)} seconds. ------")
            if not loop:
                return
            await asyncio.sleep(min(migration_list))
            continue

    @nest_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def edit_nest_reports(self, report_message, migration_local, dm_dict):
        try:
            nest_embed = report_message.embeds[0]
            edit_embed = nest_embed.description.splitlines()
            edit_embed[2] = f"**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
            nest_embed.description = ("\n").join(edit_embed)
            await report_message.edit(content=report_message.content, embed=nest_embed)
            for dm_user, dm_message in dm_dict.items():
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                await dm_message.edit(content=dm_message.content, embed=nest_embed)
        except:
            pass

    async def get_nest_reports(self, ctx):
        channel = ctx.channel
        guild = ctx.guild
        nest_dict = copy.deepcopy(ctx.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        nest_list = nest_dict.get('list', [])
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here to open the Silph Road Nest Atlas!", url="https://thesilphroad.com/atlas", description="")
        nest_embed.set_footer(text=f"Next Migration: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}")
        char_count = len(nest_embed.title) + len(nest_embed.footer.text)
        paginator = commands.Paginator(prefix="", suffix="")
        nest_count = 0
        description = ""
        if not nest_dict:
            description += _("There are no nests.")
        for nest in nest_list:
            nest_count += 1
            pkmn_dict = {}
            embed_value = "No Reports"
            report_count = 0
            nest_report_dict = nest_dict[nest]['reports']
            for report in nest_report_dict:
                report_pkmn = nest_report_dict[report]['pokemon']
                if report_pkmn in pkmn_dict:
                    pkmn_dict[report_pkmn] += 1
                else:
                    pkmn_dict[report_pkmn] = 1
            reported_pkmn = sorted(pkmn_dict.items(), key=lambda kv: kv[1], reverse=True)[:1]
            if reported_pkmn:
                embed_value = ""
            for pkmn in reported_pkmn:
                shiny_str = ""
                pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, pkmn[0])
                if pokemon.id in self.bot.shiny_dict:
                    if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                        shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
                    elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                        shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
                if report_count == 0:
                    embed_value += f"**{shiny_str}{pokemon.name.title()}** {pokemon.emoji} **({pkmn[1]})**"
                    report_count += 1
                else:
                    embed_value += f"{pokemon.name.title()} {pokemon.emoji} ({pkmn[1]})"
            description += f"**{nest_count} \u2013 {nest.title()}** | {embed_value}\n"

        for line in description.splitlines():
            paginator.add_line(line.rstrip().replace('`', '\u200b`'))

        return nest_embed, paginator.pages

    @commands.group(invoke_without_command=True)
    @checks.allownestreport()
    async def nest(self, ctx, *, pokemon=None):
        """Report a suspected nest pokemon.

        Usage: !nest <pokemon>
        Meowth will ask which nest you would like to add your report to.

        Also available:
        !nest info - to get information about a nest"""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        list_messages = []
        error = None
        await utils.safe_delete(message)
        while True:
            async with ctx.typing():
                nest_embed = discord.Embed(colour=guild.me.colour).set_thumbnail(url='https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/misc/POI_Submission_Illustration_03.png?cache=1')
                nest_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                if not pokemon:
                    nest_embed.add_field(name=_('**New Nest Report**'), value=f"Meowth! I'll help you report a nesting pokemon!\n\nFirst, I'll need to know what **pokemon** you'd like to report. Reply with the name of a **pokemon** or reply with **cancel** to stop anytime.", inline=False)
                    nest_species = await ctx.send(embed=nest_embed)
                    try:
                        species_msg = await self.bot.wait_for('message', timeout=60, check=check)
                    except asyncio.TimeoutError:
                        species_msg = None
                    await utils.safe_delete(nest_species)
                    if not species_msg:
                        error = _("took too long to respond")
                        break
                    else:
                        await utils.safe_delete(species_msg)
                    if species_msg.clean_content.lower() == "cancel":
                        error = _("cancelled the report")
                        break
                    elif species_msg:
                        await utils.safe_delete(species_msg)
                        pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, species_msg.clean_content)
                        if not pokemon:
                            error = _("entered something invalid")
                            break
                else:
                    pokemon, match_list = await pkmn_class.Pokemon.ask_pokemon(ctx, pokemon)
                    if not pokemon:
                        error = _("entered something invalid")
                        break
                pokemon.alolan = False
                pokemon.gender = None
                pokemon.form = None
                nest_types = copy.copy(pokemon.types)
                nest_types.append('None')
                nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
                nest_embed, nest_pages = await self.get_nest_reports(ctx)
                nest_embed.set_thumbnail(url=pokemon.img_url)
                nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, what's the number of the nest you'd like to add a **{pokemon}** report to?\n\nIf you want to stop your report, reply with **cancel**.".format(mention=author.mention, pokemon=pokemon.name.title()))
                list_messages.append(nest_list)
                for p in nest_pages:
                    nest_embed.description = p
                    nest_list = await channel.send(embed=nest_embed)
                    list_messages.append(nest_list)
                try:
                    nest_name_reply = await self.bot.wait_for('message', timeout=60, check=check)
                    for msg in list_messages:
                        await utils.safe_delete(msg)
                except asyncio.TimeoutError:
                    for msg in list_messages:
                        await utils.safe_delete(msg)
                    error = _("took too long to respond")
                    break
                if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
                    await utils.safe_delete(nest_name_reply)
                    error = _("cancelled the report or didn't enter a number")
                    break
                else:
                    await utils.safe_delete(nest_name_reply)
                try:
                    nest_name = nest_dict['list'][int(nest_name_reply.content)-1]
                except IndexError:
                    error = _("entered something invalid")
                break
        if not error:
            nest_loc = nest_dict[nest_name]['location'].split()
            nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_loc)}"
            nest_number = pokemon.id
            nest_img_url = pokemon.img_url
            shiny_str = ""
            if pokemon.id in self.bot.shiny_dict:
                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                    shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                    shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
            nest_description = f"**Nest**: {nest_name.title()}\n**Pokemon**: {shiny_str}{pokemon.name.title()} {pokemon.emoji}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
            nest_embed.title = f"Click here for directions to the nest!"
            nest_embed.url = nest_url
            nest_embed.description = nest_description
            nest_embed.set_thumbnail(url=nest_img_url)
            pokemon.shiny = False
            dm_dict = {}
            for trainer in self.bot.guild_dict[message.guild.id].get('trainers', {}):
                if not checks.dm_check(ctx, trainer):
                    continue
                user_wants = self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
                user_types = self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
                if nest_number in user_wants or nest_types[0].lower() in user_types or nest_types[1].lower() in user_types:
                    try:
                        user = ctx.guild.get_member(trainer)
                        nestdmmsg = await user.send(f"{author.display_name} reported that **{nest_name.title()}** is a **{str(pokemon)}** nest in {channel.mention}!", embed=nest_embed)
                        dm_dict[user.id] = nestdmmsg.id
                    except:
                        continue
            nestreportmsg = await channel.send(f"{author.mention} reported that **{nest_name.title()}** is a **{str(pokemon)}** nest!", embed=nest_embed)
            nest_dict[nest_name]['reports'][nestreportmsg.id] = {
                'exp':migration_exp,
                'expedit': "delete",
                'reportchannel':channel.id,
                'reportauthor':author.id,
                'reporttime':datetime.datetime.utcnow(),
                'dm_dict': dm_dict,
                'location':nest_name,
                'pokemon':str(pokemon)
            }
            self.bot.guild_dict[guild.id]['nest_dict'][channel.id] = nest_dict
            nest_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(message.author.id, {}).setdefault('nest_reports', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['nest_reports'] = nest_reports
        else:
            nest_embed.clear_fields()
            nest_embed.description = ""
            nest_embed.add_field(name=_('**Nest Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await ctx.send(embed=nest_embed, delete_after=10)
            await utils.safe_delete(ctx.message)

    @nest.command()
    @checks.allownestreport()
    async def info(self, ctx):
        """Shows all reports and location for a nest."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        list_messages = []

        await utils.safe_delete(message)

        if not nest_dict:
            return

        nest_embed, nest_pages = await self.get_nest_reports(ctx)

        nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, what's the number of the nest you would like more information on?\n\nIf you want to stop, reply with **cancel**.".format(mention=author.mention))
        list_messages.append(nest_list)
        for p in nest_pages:
            nest_embed.description = p
            nest_list = await channel.send(embed=nest_embed)
            list_messages.append(nest_list)

        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            for msg in list_messages:
                await utils.safe_delete(msg)
        except asyncio.TimeoutError:
            for msg in list_messages:
                await utils.safe_delete(msg)
            return
        if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
            await utils.safe_delete(nest_name_reply)
            confirmation = await channel.send(_('Request cancelled.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_name_reply)
        try:
            nest_name = nest_dict['list'][int(nest_name_reply.content)-1]
        except IndexError:
            return
        nest_loc = nest_dict[nest_name]['location'].split()
        nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_loc)}"
        pkmn_dict = {}
        embed_value = "No Reports"
        nest_img_url = ""
        report_count = 0
        nest_report_dict = nest_dict[nest_name]['reports']
        for report in nest_report_dict:
            report_pkmn = nest_report_dict[report]['pokemon']
            if report_pkmn in pkmn_dict:
                pkmn_dict[report_pkmn] += 1
            else:
                pkmn_dict[report_pkmn] = 1
        reported_pkmn = sorted(pkmn_dict.items(), key=lambda kv: kv[1], reverse=True)
        if reported_pkmn:
            embed_value = ""
        for pkmn in reported_pkmn:
            shiny_str = ""
            pokemon = pkmn_class.Pokemon.get_pokemon(self.bot, pkmn[0])
            if pokemon.id in self.bot.shiny_dict:
                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                    shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                    shiny_str = self.bot.config.get('shiny_chance', '\u2728') + " "
            if report_count == 0:
                embed_value += f"**{shiny_str}{str(pokemon)}** {pokemon.emoji} **({pkmn[1]})**"
                report_count += 1
                nest_img_url = pokemon.img_url
                nest_number = pokemon.id
            else:
                embed_value += f", {shiny_str}{str(pokemon)} {pokemon.emoji} ({pkmn[1]})"
        nest_description = f"**Nest**: {nest_name.title()}\n**All Reports**: {embed_value}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here for directions to the nest!", url=nest_url, description = nest_description)
        nest_embed.set_thumbnail(url=nest_img_url)
        info_message = await channel.send(embed=nest_embed)
        await asyncio.sleep(600)
        await utils.safe_delete(info_message)

    @nest.command()
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def add(self, ctx):
        """Adds a reportable nest for the channel."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        list_messages = []

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        nest_list = nest_dict.setdefault('list', [])

        await utils.safe_delete(message)

        nest_embed, nest_pages = await self.get_nest_reports(ctx)
        nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, what's the name of the nest you would like to add?\n\nIf you don't want to add a nest, reply with **cancel**.".format(mention=author.mention))
        list_messages.append(nest_list)
        for p in nest_pages:
            nest_embed.description = p
            nest_list = await channel.send(embed=nest_embed)
            list_messages.append(nest_list)

        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            nest_name = nest_name_reply.clean_content.lower()
            for msg in list_messages:
                await utils.safe_delete(msg)
        except asyncio.TimeoutError:
            for msg in list_messages:
                await utils.safe_delete(msg)
            return
        if nest_name_reply.content.lower() == "cancel":
            await utils.safe_delete(nest_name_reply)
            confirmation = await channel.send(_('Nest addition cancelled.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_name_reply)
        if nest_name.lower() in nest_dict.keys():
            confirmation = await channel.send(_('**{nest}** is already a nest for {channel}').format(nest=nest_name, channel=channel.mention), delete_after=10)
            return
        nest_loc_ask = await channel.send("What's the location of the **{nest}** to use for direction links? This can be GPS coordinates or an address, but I would recommend GPS if possible.\n\nIf you don't want to add a nest, reply with **cancel**.".format(nest=nest_name.title()))
        try:
            nest_loc_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            nest_loc = nest_loc_reply.clean_content
            await utils.safe_delete(nest_loc_ask)
        except asyncio.TimeoutError:
            await utils.safe_delete(nest_loc_ask)
            return
        if nest_loc_reply.content.lower() == "cancel":
            await utils.safe_delete(nest_loc_reply)
            confirmation = await channel.send(_('Nest addition cancelled.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_loc_reply)
            nest_dict[nest_name] = {
                'location':nest_loc,
                'reports': {}
            }
            self.bot.guild_dict[guild.id]['nest_dict'][channel.id] = nest_dict
            self.bot.guild_dict[guild.id]['nest_dict'][channel.id]['list'].append(nest_name)
            confirmation = await channel.send(_('Nest added.'), delete_after=10)

    @nest.command()
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def remove(self, ctx):
        """Removes a reportable nest for the channel."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        list_messages = []

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))

        await utils.safe_delete(message)

        if not nest_dict:
            return

        nest_embed, nest_pages = await self.get_nest_reports(ctx)
        nest_list = await channel.send("**Meowth!** Here's a list of all of the current nests, what's the number of the nest you would like to remove?\n\nIf you don't want to remove a nest, reply with **cancel**.")
        list_messages.append(nest_list)
        for p in nest_pages:
            nest_embed.description = p
            nest_list = await channel.send(embed=nest_embed)
            list_messages.append(nest_list)
        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            for msg in list_messages:
                await utils.safe_delete(msg)
        except asyncio.TimeoutError:
            for msg in list_messages:
                await utils.safe_delete(msg)
            return
        if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
            await utils.safe_delete(nest_name_reply)
            confirmation = await channel.send(_('Nest deletion cancelled.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_name_reply)
        try:
            nest_name = nest_dict['list'][int(nest_name_reply.content)-1]
        except IndexError:
            return
        rusure = await channel.send(_('Are you sure you\'d like to remove **{nest}** from the list of nests in {channel}?').format(nest=nest_name.title(), channel=channel.mention))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Nest deletion cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            del self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest_name]
            self.bot.guild_dict[guild.id]['nest_dict'][channel.id]['list'].remove(nest_name)
            confirmation = await channel.send(_('Nest deleted.'), delete_after=10)
            return
        else:
            return

    @nest.command(aliases=['expire'])
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx, *, report = None):
        """Migrates all nests manually, resetting all reports."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        await utils.safe_delete(message)
        if not nest_dict:
            return
        if report and report.isdigit():
            for nest in nest_dict:
                if nest == "list":
                    continue
                if int(report) in nest_dict[nest]['reports'].keys():
                    try:
                        report = await channel.fetch_message(report)
                        self.bot.loop.create_task(self.expire_nest(nest, report))
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                    return
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        list_messages = []
        nest_embed, nest_pages = await self.get_nest_reports(ctx)
        nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, reply with the number of the nest to reset or **all** to reset all nests.\n\nIf you want to stop your report, reply with **cancel**.".format(mention=author.mention))
        list_messages.append(nest_list)
        for p in nest_pages:
            nest_embed.description = p
            nest_list = await channel.send(embed=nest_embed)
            list_messages.append(nest_list)
        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=check)
            for msg in list_messages:
                await utils.safe_delete(msg)
        except asyncio.TimeoutError:
            for msg in list_messages:
                await utils.safe_delete(msg)
            return
        if nest_name_reply.content.lower() == "cancel":
            await utils.safe_delete(nest_name_reply)
            confirmation = await channel.send(_('Reset cancelled.'), delete_after=10)
            return
        elif nest_name_reply.content.lower() == "all":
            await utils.safe_delete(nest_name_reply)
            for nest in nest_dict:
                if nest == "list":
                    continue
                for report in nest_dict[nest]['reports']:
                    try:
                        report_message = await channel.fetch_message(report)
                        self.bot.loop.create_task(self.expire_nest(nest, report_message))
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
            confirmation = await channel.send(_('Nests reset. Use **!nest time** to set a new migration time.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_name_reply)
            try:
                nest_name = nest_dict['list'][int(nest_name_reply.content)-1]
            except IndexError:
                return
            for report in nest_dict[nest_name]['reports']:
                try:
                    report_message = await channel.fetch_message(report)
                    self.bot.loop.create_task(self.expire_nest(nest_name, report_message))
                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                    pass
            confirmation = await channel.send(_('Nests reset. Use **!nest time** to set a new migration time.'), delete_after=10)
            return

    async def expire_nest(self, nest, message):
        guild = message.channel.guild
        channel = message.channel
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        await utils.safe_delete(message)
        await utils.expire_dm_reports(self.bot, nest_dict[nest]['reports'][message.id].get('dm_dict', {}))
        try:
            del self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][message.id]
        except KeyError:
            pass

    @nest.command(name='time')
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def _time(self, ctx):
        """Sets the nest migration time."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))

        await utils.safe_delete(message)

        nest_time_ask = await channel.send("**Meowth!** The current nest migration is **{time}**.\n\nIf you don't want to change this, reply with **cancel**. Otherwise, what is the local date and time of the nest migration?".format(time=migration_local.strftime(_('%B %d %Y at %I:%M %p (%H:%M)'))))
        try:
            nest_time_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            await utils.safe_delete(nest_time_ask)
        except asyncio.TimeoutError:
            await utils.safe_delete(nest_time_ask)
            return
        if nest_time_reply.content.lower() == "cancel":
            await utils.safe_delete(nest_time_reply)
            confirmation = await channel.send(_('Migration time set cancelled.'), delete_after=10)
            return
        else:
            await utils.safe_delete(nest_time_reply)
        migration_local = dateparser.parse(nest_time_reply.clean_content, settings={'RETURN_AS_TIMEZONE_AWARE': False})
        migration_utc = migration_local - datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        rusure = await channel.send(_('Are you sure you\'d like to set the next migration to **{time}**?\n\nThis will also set all current nest reports to expire at this new time.').format(time=migration_local.strftime(_('%B %d %Y at %I:%M %p (%H:%M)'))))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.config.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Migration time set cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.config.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            ctx.bot.guild_dict[guild.id]['configure_dict']['nest']['migration'] = migration_utc
            for nest in nest_dict:
                for report in nest_dict[nest]['reports']:
                    self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][report]['exp'] = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
                    try:
                        report_message = await channel.fetch_message(report)
                    except:
                        continue
                    await self.edit_nest_reports(report_message, migration_local, nest_dict[nest]['reports'][report]['dm_dict'])
            confirmation = await channel.send(_('Migration time set.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Nest(bot))

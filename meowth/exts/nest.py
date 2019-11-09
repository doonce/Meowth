import asyncio
import copy
import re
import time
import datetime
import dateparser
import logging
import traceback

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
        logger.info('------ BEGIN ------')
        migration_list = []
        count = 0
        try:
            for guild in list(self.bot.guilds):
                nest_dict = self.bot.guild_dict[guild.id].setdefault('nest_dict', {})
                utcnow = datetime.datetime.utcnow()
                migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest']['migration']
                new_migration = False
                if utcnow > migration_utc:
                    new_migration = migration_utc + datetime.timedelta(days=14)
                    migration_local = new_migration + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
                    self.bot.guild_dict[guild.id]['configure_dict']['nest']['migration'] = new_migration
                to_migration = migration_utc.timestamp() - utcnow.timestamp()
                if to_migration > 0:
                    migration_list.append(to_migration)
                for channel in list(nest_dict.keys()):
                    report_channel = self.bot.get_channel(channel)
                    if not report_channel:
                        del self.bot.guild_dict[guild.id]['nest_dict'][channel]
                        logger.info(f"Deleted Nest Channel {report_channel}")
                        continue
                    for nest in nest_dict.get(channel, {}):
                        if nest == 'list':
                            continue
                        for report in list(nest_dict.get(channel, {}).get(nest, {}).get('reports', {}).keys()):
                            if nest_dict[channel][nest]['reports'][report].get('exp', 0) <= time.time():
                                try:
                                    report_message = await report_channel.fetch_message(report)
                                    if new_migration and nest_dict[channel][nest]['reports'][report]['reporttime'] > migration_utc:
                                        ctx = self.bot.get_context(report_message)
                                        self.bot.guild_dict[guild.id]['nest_dict'][channel][nest]['reports'][report]['exp'] = new_migration.replace(tzinfo=datetime.timezone.utc).timestamp()
                                        self.bot.loop.create_task(self.edit_nest_messages(ctx, nest, report_message))
                                        count += 1
                                        continue
                                    self.bot.loop.create_task(self.expire_nest(nest, report_message))
                                    count += 1
                                except:
                                    pass

            if not migration_list:
                migration_list = [600]
            logger.info(f"------ END - {count} Nests Cleaned - Waiting {min(migration_list)} seconds. ------")
            if not loop:
                return
            self.nest_cleanup.change_interval(seconds=min(migration_list))
        except Exception as e:
            print(traceback.format_exc())

    @nest_cleanup.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    async def expire_nest(self, nest, message):
        guild = message.channel.guild
        channel = message.channel
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        author = guild.get_member(nest_dict.get(nest, {}).get('reports', {}).get(message.id, {}).get('report_author'))
        await utils.safe_delete(message)
        self.bot.loop.create_task(utils.expire_dm_reports(self.bot, nest_dict[nest]['reports'][message.id].get('dm_dict', {})))
        nest_bonus = nest_dict[nest]['reports'].get(message.id, {}).get('caught_by', [])
        if len(nest_bonus) >= 3 and author and not author.bot:
            nest_reports = self.bot.guild_dict[message.guild.id].setdefault('trainers', {}).setdefault(author.id, {}).setdefault('reports', {}).setdefault('nest', 0) + 1
            self.bot.guild_dict[message.guild.id]['trainers'][author.id]['reports']['nest'] = nest_reports
        try:
            del self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][message.id]
        except KeyError:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        guild = getattr(channel, "guild", None)
        try:
            user = self.bot.get_user(payload.user_id)
        except AttributeError:
            return
        if user == self.bot.user:
            return
        if guild:
            user = guild.get_member(payload.user_id)
        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.errors.NotFound, AttributeError, discord.Forbidden):
            return
        ctx = await self.bot.get_context(message)
        can_manage = channel.permissions_for(user).manage_messages
        if not can_manage and user.id in self.bot.config.managers:
            can_manage = True
        try:
            nest_dict = self.bot.guild_dict[guild.id]['nest_dict']
        except KeyError:
            nest_dict = {}
        if channel.id in nest_dict:
            for nest in nest_dict[channel.id]:
                if nest == "list":
                    continue
                if message.id in nest_dict[channel.id][nest].get('reports'):
                    if str(payload.emoji) == self.bot.custom_emoji.get('wild_catch', '\U0001f1f7'):
                        if user.id not in nest_dict[channel.id][nest]['reports'][message.id].get('caught_by', []):
                            if user.id != nest_dict[channel.id][nest]['reports'][message.id]['report_author']:
                                nest_dict[channel.id][nest]['reports'][message.id].setdefault('caught_by', []).append(user.id)
                    elif str(payload.emoji) == self.bot.custom_emoji.get('nest_expire', '\U0001F4A8'):
                        for reaction in message.reactions:
                            if reaction.emoji == self.bot.custom_emoji.get('nest_expire', '\U0001F4A8') and (reaction.count >= 3 or can_manage):
                                await self.expire_nest(nest, message)
                    elif str(payload.emoji) == self.bot.custom_emoji.get('nest_info', '\u2139'):
                        if not ctx.prefix:
                            prefix = self.bot._get_prefix(self.bot, message)
                            ctx.prefix = prefix[-1]
                        await message.remove_reaction(payload.emoji, user)
                        ctx.author = user
                        if user.id == nest_dict[channel.id][nest]['reports'][message.id]['report_author'] or can_manage:
                            await self.edit_nest_info(ctx, message)
                    elif str(payload.emoji) == self.bot.custom_emoji.get('nest_report', '\U0001F4E2'):
                        ctx = await self.bot.get_context(message)
                        ctx.author, ctx.message.author = user, user
                        await message.remove_reaction(payload.emoji, user)
                        return await ctx.invoke(self.bot.get_command('nest'))
                    elif str(payload.emoji) == self.bot.custom_emoji.get('list_emoji', '\U0001f5d2'):
                        ctx = await self.bot.get_context(message)
                        await asyncio.sleep(0.25)
                        await message.remove_reaction(payload.emoji, self.bot.user)
                        await asyncio.sleep(0.25)
                        await message.remove_reaction(payload.emoji, user)
                        await ctx.invoke(self.bot.get_command("list nests"))
                        await asyncio.sleep(5)
                        return await utils.safe_reaction(message, payload.emoji)

    async def edit_nest_info(self, ctx, message):
        nest_dict = self.bot.guild_dict[ctx.guild.id]['nest_dict'].get(ctx.channel.id, {})
        for nest in nest_dict:
            if nest == "list":
                continue
            if message.id in list(nest_dict[nest].get('reports', {}).keys()):
                location = nest
                break
        nest_dict = self.bot.guild_dict[ctx.guild.id]['nest_dict'].get(ctx.channel.id, {}).get(location, {}).get('reports', {}).get(message.id, {})
        message = ctx.message
        channel = message.channel
        guild = message.guild
        author = guild.get_member(nest_dict.get('report_author', None))
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, nest_dict.get('pokemon'))
        if not author or not location:
            return
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[channel.guild.id]['configure_dict']['settings']['offset']))
        error = False
        entered_pokemon = None
        success = []
        reply_msg = f"**pokemin <nest species>** - Current: {nest_dict.get('pokemon', 'X')}\n"
        nest_embed = discord.Embed(colour=message.guild.me.colour).set_thumbnail(url=pokemon.img_url)
        nest_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp.strftime(_('%I:%M %p (%H:%M)'))), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        while True:
            async with ctx.typing():
                nest_embed.add_field(name=_('**Edit Nest Report Info**'), value=f"Meowth! I'll help you edit information of the **{str(pokemon)}** nest report at **{location.title()}**!\n\nI'll need to know what **values** you'd like to edit. Reply **cancel** to stop anytime or reply with a comma separated list of the following options `Ex: pokemon pikachu`:\n\n{reply_msg}", inline=False)
                value_wait = await channel.send(embed=nest_embed)
                def check(reply):
                    if reply.author is not guild.me and reply.channel.id == channel.id and reply.author == ctx.author:
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
                    entered_values = value_msg.clean_content.lower().split(',')
                    entered_values = [x.strip() for x in entered_values]
                    for value in entered_values:
                        value_split = value.split()
                        if len(value_split) < 2:
                            error = _("entered something invalid")
                            continue
                        if "pokemon" in value and "pokemon" not in success:
                            entered_pokemon, __ = await pkmn_class.Pokemon.ask_pokemon(ctx, value.replace('pokemon', ''))
                            if value_split[1] and entered_pokemon:
                                self.bot.guild_dict[ctx.guild.id]['nest_dict'][channel.id][location]['reports'][message.id]['pokemon'] = value_split[1]
                                success.append("pokemon")
                            else:
                                error = _('entered something invalid. Check your pokemon spelling.')
                        else:
                            error = _("entered something invalid")
                    break
        if not entered_pokemon:
            entered_pokemon = pokemon
        if success:
            await self.edit_nest_messages(ctx, location, message)
        else:
            error = _("didn't change anything")
        if error:
            nest_embed.clear_fields()
            nest_embed.add_field(name=_('**Nest Report Edit Cancelled**'), value=f"Meowth! Your edit has been cancelled because you **{error}**! Retry when you're ready.", inline=False)
            if success:
                nest_embed.set_field_at(0, name="**Nest Report Edit Error**", value=f"Meowth! Your **{(', ').join(success)}** edits were successful, but others were skipped because you **{error}**! Retry when you're ready.", inline=False)
            confirmation = await channel.send(embed=nest_embed, delete_after=10)

    async def edit_nest_messages(self, ctx, location, message):
        nest_dict = self.bot.guild_dict[ctx.guild.id]['nest_dict'].get(ctx.channel.id, {}).get(location, {}).get('reports', {}).get(message.id, {})
        dm_dict = nest_dict.get('dm_dict', {})
        pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, nest_dict.get('pokemon'))
        nest_embed = message.embeds[0]
        author = ctx.guild.get_member(nest_dict.get('report_author', None))
        if author:
            ctx.author = author
        migration_utc = self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        nest_embed.set_thumbnail(url=pokemon.img_url)
        shiny_str = ""
        if pokemon.id in self.bot.shiny_dict:
            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
        nest_embed.description = f"**Nest**: {location.title()}\n**Pokemon**: {shiny_str}{pokemon.name.title()} {pokemon.emoji}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
        result = re.search(r'Meowth! (.*) nest', message.content).group(1)
        message.content = message.content.replace(result, str(pokemon))
        try:
            await message.edit(content=message.content, embed=nest_embed)
        except:
            pass
        if isinstance(nest_embed.description, discord.embeds._EmptyEmbed):
            nest_embed.description = ""
        if "Jump to Message" not in nest_embed.description:
            nest_embed.description = nest_embed.description + f"\n**Report:** [Jump to Message]({message.jump_url})"
        index = 0
        for dm_user, dm_message in dm_dict.items():
            try:
                dm_user = self.bot.get_user(dm_user)
                dm_channel = dm_user.dm_channel
                if not dm_channel:
                    dm_channel = await dm_user.create_dm()
                if not dm_user or not dm_channel:
                    continue
                dm_message = await dm_channel.fetch_message(dm_message)
                content = dm_message.content.replace(result, str(pokemon))
                await dm_message.edit(content=content, embed=nest_embed)
            except:
                pass
        ctx.nestreportmsg = message
        dm_dict = await self.send_dm_messages(ctx, location, pokemon, copy.deepcopy(nest_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.channel.id][location]['reports'][message.id]['dm_dict'] = dm_dict

    async def get_nest_reports(self, ctx):
        channel = ctx.channel
        guild = ctx.guild
        nest_dict = copy.deepcopy(ctx.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        nest_list = nest_dict.get('list', [])
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here to open the Silph Road Nest Atlas!", url="https://thesilphroad.com/atlas", description=f"Use **{ctx.prefix}nest info** for more information about a nest.")
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
            reported_pkmn = sorted(pkmn_dict.items(), key=lambda kv: kv[1], reverse=True)[:2]
            if reported_pkmn:
                embed_value = ""
            for pkmn in reported_pkmn:
                shiny_str = ""
                pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn[0])
                if pokemon.id in self.bot.shiny_dict:
                    if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                        shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                    elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                        shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                if report_count == 0:
                    embed_value += f"**{shiny_str}{pokemon.name.title()}** {pokemon.emoji}"
                    if len(reported_pkmn) > 1:
                        embed_value += f" **({pkmn[1]})**"
                    report_count += 1
                else:
                    embed_value += f", {shiny_str}{pokemon.name.title()} {pokemon.emoji}"
                    if len(reported_pkmn) > 1:
                        embed_value += f" ({pkmn[1]})"
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
        list_messages = []
        error = None
        if not message.embeds:
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
            await self.send_nest(ctx, nest_name, pokemon)
        else:
            nest_embed.clear_fields()
            nest_embed.description = ""
            nest_embed.add_field(name=_('**Nest Report Cancelled**'), value=_("Meowth! Your report has been cancelled because you {error}! Retry when you're ready.").format(error=error), inline=False)
            confirmation = await ctx.send(embed=nest_embed, delete_after=10)
            await utils.safe_delete(ctx.message)

    async def send_nest(self, ctx, nest_name, pokemon):
        nest_dict = self.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.channel.id]
        expire_emoji = self.bot.custom_emoji.get('nest_expire', '\U0001F4A8')
        catch_emoji = ctx.bot.custom_emoji.get('wild_catch', '\u26BE')
        info_emoji = ctx.bot.custom_emoji.get('nest_info', '\u2139')
        report_emoji = ctx.bot.custom_emoji.get('nest_report', '\U0001F4E2')
        list_emoji = self.bot.custom_emoji.get('list_emoji', '\U0001f5d2')
        react_list = [catch_emoji, expire_emoji, info_emoji, report_emoji, list_emoji]
        nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_name.split())}"
        migration_utc = self.bot.guild_dict[ctx.guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        shiny_str = ""
        if pokemon.id in self.bot.shiny_dict:
            if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
            elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
        nest_description = f"**Nest**: {nest_name.title()}\n**Pokemon**: {shiny_str}{pokemon.name.title()} {pokemon.emoji}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
        nest_embed = discord.Embed(colour=ctx.guild.me.colour)
        nest_embed.title = f"Click here for directions to the nest!"
        nest_embed.url = nest_url
        nest_embed.description = nest_description
        nest_embed.set_thumbnail(url=pokemon.img_url)
        pokemon.shiny = False
        dm_dict = {}
        ctx.nestreportmsg = await ctx.send(f"Meowth! {str(pokemon)} nest reported by {ctx.author.mention}! Details: {nest_name.title()}!\n\nUse {catch_emoji} if you visited, {expire_emoji} if expired, {info_emoji} to edit details, {report_emoji} to report new, or {list_emoji} to list all nests!", embed=nest_embed)
        for reaction in react_list:
            await asyncio.sleep(0.25)
            await utils.safe_reaction(ctx.nestreportmsg, reaction)
        nest_dict[nest_name]['reports'][ctx.nestreportmsg.id] = {
            'exp':migration_exp,
            'expedit': "delete",
            'report_channel':ctx.channel.id,
            'report_author':ctx.author.id,
            'report_guild':ctx.guild.id,
            'report_time':time.time(),
            'dm_dict': dm_dict,
            'location':nest_name,
            'pokemon':str(pokemon)
        }
        self.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.channel.id] = nest_dict
        dm_dict = await self.send_dm_messages(ctx, nest_name, pokemon, copy.deepcopy(nest_embed), dm_dict)
        self.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.channel.id][nest_name]['reports'][ctx.nestreportmsg.id]['dm_dict'] = dm_dict
        if not ctx.author.bot:
            nest_reports = ctx.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).setdefault(ctx.author.id, {}).setdefault('reports', {}).setdefault('nest', 0) + 1
            self.bot.guild_dict[ctx.guild.id]['trainers'][ctx.author.id]['reports']['nest'] = nest_reports

    async def send_dm_messages(self, ctx, nest_name, pokemon, embed, dm_dict):
        if embed:
            if isinstance(embed.description, discord.embeds._EmptyEmbed):
                embed.description = ""
            if "Jump to Message" not in embed.description:
                embed.description = embed.description + f"\n**Report:** [Jump to Message]({ctx.nestreportmsg.jump_url})"
            index = 0
            for field in embed.fields:
                if "reaction" in field.name.lower():
                    embed.remove_field(index)
                else:
                    index += 1
        nest_types = copy.copy(pokemon.types)
        nest_types.append('None')
        for trainer in self.bot.guild_dict[ctx.guild.id].get('trainers', {}):
            user_wants = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('wants', [])
            user_forms = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('forms', [])
            pokemon_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('pokemon', {}).get('nest', True)
            user_types = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].setdefault('alerts', {}).setdefault('types', [])
            type_setting = self.bot.guild_dict[ctx.guild.id].get('trainers', {})[trainer].get('alerts', {}).get('settings', {}).get('categories', {}).get('type', {}).get('nest', True)
            if not any([user_wants, user_forms, pokemon_setting, user_types, type_setting]):
                continue
            if not checks.dm_check(ctx, trainer) or trainer in dm_dict:
                continue
            send_nest = False
            if pokemon_setting and pokemon and (pokemon.id in user_wants or str(pokemon) in user_forms):
                send_nest = True
            if type_setting and (nest_types[0].lower() in user_types or nest_types[1].lower() in user_types):
                send_nest = True
            if send_nest:
                try:
                    user = ctx.guild.get_member(trainer)
                    nestdmmsg = await user.send(f"Meowth! {str(pokemon)} nest reported by {ctx.author.display_name} in {ctx.channel.mention}! Details: {nest_name.title()}", embed=embed)
                    dm_dict[user.id] = nestdmmsg.id
                except:
                    continue
        return dm_dict

    @nest.command()
    @checks.allownestreport()
    async def info(self, ctx):
        """Shows all reports and location for a nest.

        Usage: !nest info"""
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
            pokemon = await pkmn_class.Pokemon.async_get_pokemon(self.bot, pkmn[0])
            if pokemon.id in self.bot.shiny_dict:
                if pokemon.alolan and "alolan" in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get("alolan", []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
                elif str(pokemon.form).lower() in self.bot.shiny_dict.get(pokemon.id, {}) and "wild" in self.bot.shiny_dict.get(pokemon.id, {}).get(str(pokemon.form).lower(), []):
                    shiny_str = self.bot.custom_emoji.get('shiny_chance', '\u2728') + " "
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
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Nest deletion cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            for report in copy.deepcopy(self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest_name].get('reports', {})):
                try:
                    report_message = await channel.fetch_message(report)
                    await self.expire_nest(nest_name, report_message)
                except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                    pass
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
        """Migrates all nests manually, resetting all reports.

        Usage: !nest reset [message ID]
        Will either reset [message], or ask which nest to reset if no message is supplied"""
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
            async with ctx.typing():
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
            async with ctx.typing():
                for report in nest_dict[nest_name]['reports']:
                    try:
                        report_message = await channel.fetch_message(report)
                        self.bot.loop.create_task(self.expire_nest(nest_name, report_message))
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                confirmation = await channel.send(f"{nest_name.title()} reset. Use **!nest time** to set a new migration time.", delete_after=10)
            return

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
        if not migration_local:
            return await channel.send(f"I couldn't understand your time. Migration time set cancelled.")
        migration_utc = migration_local - datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        rusure = await channel.send(_('Are you sure you\'d like to set the next migration to **{time}**?\n\nThis will also set all current nest reports to expire at this new time.').format(time=migration_local.strftime(_('%B %d %Y at %I:%M %p (%H:%M)'))))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == self.bot.custom_emoji.get('answer_no', '\u274e'):
            await utils.safe_delete(rusure)
            confirmation = await channel.send(_('Migration time set cancelled.'), delete_after=10)
            return
        elif res.emoji == self.bot.custom_emoji.get('answer_yes', '\u2705'):
            await utils.safe_delete(rusure)
            ctx.bot.guild_dict[guild.id]['configure_dict']['nest']['migration'] = migration_utc
            for nest in nest_dict:
                if nest == "list":
                    continue
                for report in nest_dict[nest]['reports']:
                    self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][report]['exp'] = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
                    try:
                        report_message = await channel.fetch_message(report)
                    except:
                        continue
                    await self.edit_nest_messages(ctx, nest, report_message)
            confirmation = await channel.send(_('Migration time set.'), delete_after=10)
            return
        else:
            return

def setup(bot):
    bot.add_cog(Nest(bot))

def teardown(bot):
    bot.remove_cog(Nest)

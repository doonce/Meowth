import asyncio
import copy
import re
import time
import datetime
import dateparser

import discord
from discord.ext import commands

from meowth import utils, checks

class Nest:
    def __init__(self, bot):
        self.bot = bot

    # nest_dict:{
    #     nestrepotchannel_id: {
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
    #                     'pokemon':entered_nest
    #                 }
    #             }
    #         }
    #     }
    # }

    async def nest_cleanup(self, loop=True):
        while (not self.bot.is_closed()):
            guilddict_temp = copy.deepcopy(self.bot.guild_dict)
            for guildid in guilddict_temp.keys():
                nest_dict = guilddict_temp[guildid].setdefault('nest_dict',{})
                utcnow = datetime.datetime.utcnow()
                migration_utc = guilddict_temp[guildid]['configure_dict']['nest']['migration']
                new_migration = False
                if utcnow > migration_utc:
                    new_migration = migration_utc + datetime.timedelta(days=14)
                    migration_local = new_migration + datetime.timedelta(hours=self.bot.guild_dict[guildid]['configure_dict']['settings']['offset'])
                    self.bot.guild_dict[guildid]['configure_dict']['nest']['migration'] = new_migration
                for channel in nest_dict:
                    report_channel = self.bot.get_channel(channel)
                    if not report_channel:
                        del self.bot.guild_dict[guildid]['nest_dict'][channel]
                        continue
                    for nest in nest_dict[channel]:
                        for report in nest_dict[channel][nest]['reports']:
                            if nest_dict[channel][nest]['reports'][report].get('exp', 0) <= time.time():
                                try:
                                    report_message = await report_channel.get_message(report)
                                    if new_migration and nest_dict[channel][nest]['reports'][report]['reporttime'] > migration_utc:
                                        self.bot.guild_dict[guildid]['nest_dict'][channel][nest]['reports'][report]['exp'] = new_migration.replace(tzinfo=datetime.timezone.utc).timestamp()
                                        nest_embed = report_message.embeds[0]
                                        edit_embed = nest_embed.description.splitlines()
                                        edit_embed[2] = f"**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
                                        nest_embed.description = ("\n").join(edit_embed)
                                        await report_message.edit(content=report_message.content, embed=nest_embed)
                                        for dm_user, dm_message in nest_dict[channel][nest]['reports'][report]['dm_dict'].items():
                                            dm_user = self.bot.get_user(dm_user)
                                            dm_channel = dm_user.dm_channel
                                            if not dm_channel:
                                                dm_channel = await dm_user.create_dm()
                                            if not dm_user or not dm_channel:
                                                continue
                                            dm_message = await dm_channel.get_message(dm_message)
                                            await dm_message.edit(content=dm_message.content, embed=nest_embed)
                                        continue
                                    await report_message.delete()
                                    await utils.expire_dm_reports(self.bot, nest_dict[channel][nest]['reports'][report].get('dm_dict', {}))
                                    del self.bot.guild_dict[guildid]['nest_dict'][channel][nest]['reports'][report]
                                except:
                                    pass
            await asyncio.sleep(600)
            continue

    async def get_nest_reports(self, ctx):
        channel = ctx.channel
        guild = ctx.guild
        nest_dict = copy.deepcopy(ctx.bot.guild_dict[guild.id].setdefault('nest_dict',{}).setdefault(channel.id, {}))
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here to open the Silph Road Nest Atlas!", url="https://thesilphroad.com/atlas", description="")
        nest_embed.set_footer(text=f"Next Migration: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}")
        char_count = len(nest_embed.title) + len(nest_embed.footer.text)
        nest_count = 0
        if not nest_dict:
            nest_embed.description += _("There are no nests.")
            return nest_embed
        for nest in nest_dict:
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
                if report_count == 0:
                    embed_value += f"**{pkmn[0].title()} ({pkmn[1]})** "
                    report_count += 1
                else:
                    embed_value += f"{pkmn[0].title()} ({pkmn[1]}) "
            char_count += len(nest_embed.description)
            if char_count < (5950 - len(f"**{nest_count} \u2013 {nest}** | {embed_value}\n")):
                nest_embed.description += f"**{nest_count} \u2013 {nest}** | {embed_value}\n"
            else:
                nest_embed.description += f"\n**NEST LIMIT REACHED FOR THIS CHANNEL**"
                break

        return nest_embed

    @commands.group(invoke_without_command=True)
    @checks.allownestreport()
    async def nest(self, ctx, pokemon):
        """Report a suspected nest pokemon.

        Usage: !nest <pokemon>
        Meowth will ask which nest you would like to add your report to."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel
        timestamp = (message.created_at + datetime.timedelta(hours=self.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])).strftime(_('%I:%M %p (%H:%M)'))
        migration_utc = self.bot.guild_dict[guild.id]['configure_dict']['nest'].setdefault('migration', datetime.datetime.utcnow() + datetime.timedelta(days=14))
        migration_local = migration_utc + datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        migration_exp = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()

        await message.delete()
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))
        entered_nest = pokemon
        entered_nest = utils.get_name(entered_nest).lower() if entered_nest.isdigit() else entered_nest
        rgx = '[^a-zA-Z0-9]'
        pkmn_match = next((p for p in self.bot.pkmn_info['pokemon_list'] if re.sub(rgx, '', p) == re.sub(rgx, '', entered_nest)), None)
        if pkmn_match:
            entered_nest = pkmn_match
        else:
            entered_nest = await utils.autocorrect(self.bot, entered_nest, channel, author)
        if not entered_nest:
            return
        entered_pkmn = entered_nest.title()
        nest_embed = await self.get_nest_reports(ctx)
        nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, what's the number of the nest you'd like to add a {pokemon} report to\n\nIf you want to stop your report, reply with **cancel**.?".format(mention=author.mention, pokemon=entered_nest.title()), embed=nest_embed)
        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            await nest_list.delete()
        except asyncio.TimeoutError:
            await nest_list.delete()
            return
        if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
            await nest_name_reply.delete()
            confirmation = await channel.send(_('Report cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_name_reply.delete()
        nest_name = nest_embed.description.splitlines()[int(nest_name_reply.content)-1].split("\u2013")[1].split("**")[0].strip().title()
        nest_loc = nest_dict[nest_name]['location'].split()
        nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_loc)}"
        nest_number = self.bot.pkmn_info['pokemon_list'].index(entered_nest) + 1
        nest_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/{0}_.png?cache=0'.format(str(nest_number).zfill(3))
        nest_description = f"**Nest**: {nest_name.title()}\n**Pokemon**: {entered_nest.title()}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here for directions to the nest!", url=nest_url, description = nest_description)
        nest_embed.set_thumbnail(url=nest_img_url)
        nest_embed.set_footer(text=_('Reported by @{author} - {timestamp}').format(author=author.display_name, timestamp=timestamp), icon_url=author.avatar_url_as(format=None, static_format='jpg', size=32))
        dm_dict = {}
        for trainer in self.bot.guild_dict[message.guild.id].get('trainers', {}):
            user = message.guild.get_member(trainer)
            if not user:
                continue
            perms = user.permissions_in(message.channel)
            if not perms.read_messages:
                continue
            if nest_number in self.bot.guild_dict[message.guild.id].get('trainers', {})[trainer].setdefault('wants', []):
                nestdmmsg = await user.send(f"{author.display_name} reported that **{nest_name}** is a **{entered_pkmn}** nest in {channel.mention}!", embed=nest_embed)
                dm_dict[user.id] = nestdmmsg.id
        nestreportmsg = await channel.send(f"{author.mention} reported that **{nest_name}** is a **{entered_pkmn}** nest!", embed=nest_embed)
        nest_dict[nest_name]['reports'][nestreportmsg.id] = {
            'exp':migration_exp,
            'expedit': "delete",
            'reportchannel':channel.id,
            'reportauthor':author.id,
            'reporttime':datetime.datetime.utcnow(),
            'dm_dict': dm_dict,
            'location':nest_name,
            'pokemon':entered_nest
        }
        self.bot.guild_dict[guild.id]['nest_dict'][channel.id] = nest_dict
        nest_reports = ctx.bot.guild_dict[message.guild.id].setdefault('trainers',{}).setdefault(message.author.id,{}).setdefault('nest_reports',0) + 1
        self.bot.guild_dict[message.guild.id]['trainers'][message.author.id]['nest_reports'] = nest_reports

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

        await message.delete()

        if not nest_dict:
            return

        nest_embed = await self.get_nest_reports(ctx)

        nest_list = await channel.send("**Meowth!** Here's a list of all of the current nests, what's the number of the nest you would like more information on?\n\nIf you want to stop, reply with **cancel**.", embed=nest_embed)

        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            await nest_list.delete()
        except asyncio.TimeoutError:
            await nest_list.delete()
            return
        if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
            await nest_name_reply.delete()
            confirmation = await channel.send(_('Request cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_name_reply.delete()
        nest_name = nest_embed.description.splitlines()[int(nest_name_reply.content)-1].split("\u2013")[1].split("**")[0].strip().title()
        nest_loc = nest_dict[nest_name]['location'].split()
        nest_url = f"https://www.google.com/maps/search/?api=1&query={('+').join(nest_loc)}"
        pkmn_dict = {}
        embed_value = "No Reports"
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
            if report_count == 0:
                embed_value += f"**{pkmn[0].title()} ({pkmn[1]})** "
                report_count += 1
                nest_number = self.bot.pkmn_info['pokemon_list'].index(pkmn[0]) + 1
            else:
                embed_value += f"{pkmn[0].title()} ({pkmn[1]}) "
        nest_img_url = 'https://raw.githubusercontent.com/doonce/Meowth/Rewrite/images/pkmn/{0}_.png?cache=0'.format(str(nest_number).zfill(3))
        nest_description = f"**Nest**: {nest_name.title()}\n**All Reports**: {embed_value}\n**Migration**: {migration_local.strftime(_('%B %d at %I:%M %p (%H:%M)'))}"
        nest_embed = discord.Embed(colour=guild.me.colour, title="Click here for directions to the nest!", url=nest_url, description = nest_description)
        nest_embed.set_thumbnail(url=nest_img_url)
        info_message = await channel.send(embed=nest_embed)
        await asyncio.sleep(60)
        await info_message.delete()

    @nest.command()
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def add(self, ctx):
        """Adds a reportable nest for the channel."""
        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))

        await message.delete()

        nest_embed = await self.get_nest_reports(ctx)
        nest_list = await channel.send("**Meowth!** {mention}, here's a list of all of the current nests, what's the name of the nest you would like to add?\n\nIf you don't want to add a nest, reply with **cancel**.".format(mention=author.mention), embed=nest_embed)

        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            nest_name = nest_name_reply.clean_content.title()
            await nest_list.delete()
        except asyncio.TimeoutError:
            await nest_list.delete()
            return
        if nest_name_reply.content.lower() == "cancel":
            await nest_name_reply.delete()
            confirmation = await channel.send(_('Nest addition cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_name_reply.delete()
        if nest_name.title() in nest_dict.keys():
            confirmation = await channel.send(_('**{nest}** is already a nest for {channel}').format(nest=nest_name, channel=channel.mention))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        nest_loc_ask = await channel.send("What's the location of the **{nest}** to use for direction links? This can be GPS coordinates or an address, but I would recommend GPS if possible.\n\nIf you don't want to add a nest, reply with **cancel**.".format(nest=nest_name))
        try:
            nest_loc_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            nest_loc = nest_loc_reply.clean_content
            await nest_loc_ask.delete()
        except asyncio.TimeoutError:
            await nest_loc_ask.delete()
            return
        if nest_loc_reply.content.lower() == "cancel":
            await nest_loc_reply.delete()
            confirmation = await channel.send(_('Nest addition cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_loc_reply.delete()
        rusure = await channel.send(_('Are you sure you\'d like to add **{nest}** to the list of nests in {channel}?').format(nest=nest_name, channel=channel.mention))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == '❎':
            await rusure.delete()
            confirmation = await channel.send(_('Nest addition cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        elif res.emoji == '✅':
            await rusure.delete()
            nest_dict[nest_name] = {
                'location':nest_loc,
                'reports': {}
            }
            self.bot.guild_dict[guild.id]['nest_dict'][channel.id] = nest_dict
            confirmation = await channel.send(_('Nest added.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            return

    @nest.command()
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def remove(self, ctx):
        """Removes a reportable nest for the channel."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))

        await message.delete()

        if not nest_dict:
            return

        nest_embed = await self.get_nest_reports(ctx)

        nest_list = await channel.send("**Meowth!** Here's a list of all of the current nests, what's the number of the nest you would like to remove?\n\nIf you don't want to remove a nest, reply with **cancel**.", embed=nest_embed)

        try:
            nest_name_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            await nest_list.delete()
        except asyncio.TimeoutError:
            await nest_list.delete()
            return
        if nest_name_reply.content.lower() == "cancel" or not nest_name_reply.content.isdigit():
            await nest_name_reply.delete()
            confirmation = await channel.send(_('Nest deletion cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_name_reply.delete()
        nest_name = nest_embed.description.splitlines()[int(nest_name_reply.content)-1].split("\u2013")[1].split("**")[0].strip().title()
        rusure = await channel.send(_('Are you sure you\'d like to remove **{nest}** from the list of nests in {channel}?').format(nest=nest_name, channel=channel.mention))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == '❎':
            await rusure.delete()
            confirmation = await channel.send(_('Nest deletion cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        elif res.emoji == '✅':
            await rusure.delete()
            del self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest_name]
            confirmation = await channel.send(_('Nest deleted.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            return

    @nest.command()
    @checks.allownestreport()
    @commands.has_permissions(manage_channels=True)
    async def reset(self, ctx):
        """Migrates all nests manually, resetting all reports."""

        author = ctx.author
        guild = ctx.guild
        message = ctx.message
        channel = ctx.channel

        # get settings
        nest_dict = copy.deepcopy(self.bot.guild_dict[guild.id].setdefault('nest_dict', {}).setdefault(channel.id, {}))

        await message.delete()

        if not nest_dict:
            return
        rusure = await channel.send(_('**Meowth!** Are you sure you\'d like to remove all reports for all nests?'))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == '❎':
            await rusure.delete()
            confirmation = await channel.send(_('Manual reset cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        elif res.emoji == '✅':
            await rusure.delete()
            for nest in nest_dict:
                for report in nest_dict[nest]['reports']:
                    report_message = await channel.get_message(report)
                    try:
                        await report_message.delete()
                    except (discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                    del self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][report]
                    await utils.expire_dm_reports(self.bot, nest_dict[nest]['reports'][report].get('dm_dict', {}))
            confirmation = await channel.send(_('Nests reset. Use **!nest time** to set a new migration time.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
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

        await message.delete()

        nest_time_ask = await channel.send("**Meowth!** The current nest migration is **{time}**.\n\nIf you don't want to change this, reply with **cancel**. Otherwise, what is the local date and time of the nest migration?".format(time=migration_local.strftime(_('%B %d %Y at %I:%M %p (%H:%M)'))))
        try:
            nest_time_reply = await self.bot.wait_for('message', timeout=60, check=(lambda message: (message.author == author)))
            await nest_time_ask.delete()
        except asyncio.TimeoutError:
            await nest_time_ask.delete()
            return
        if nest_time_reply.content.lower() == "cancel":
            await nest_time_reply.delete()
            confirmation = await channel.send(_('Migration time set cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            await nest_time_reply.delete()
        migration_local = dateparser.parse(nest_time_reply.clean_content, settings={'RETURN_AS_TIMEZONE_AWARE': False})
        migration_utc = migration_local - datetime.timedelta(hours=ctx.bot.guild_dict[guild.id]['configure_dict']['settings']['offset'])
        rusure = await channel.send(_('Are you sure you\'d like to set the next migration to **{time}**?\n\nThis will also set all current nest reports to expire at this new time.').format(time=migration_local.strftime(_('%B %d %Y at %I:%M %p (%H:%M)'))))
        try:
            timeout = False
            res, reactuser = await utils.ask(self.bot, rusure, author.id)
        except TypeError:
            timeout = True
        if timeout or res.emoji == '❎':
            await rusure.delete()
            confirmation = await channel.send(_('Migration time set cancelled.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        elif res.emoji == '✅':
            await rusure.delete()
            ctx.bot.guild_dict[guild.id]['configure_dict']['nest']['migration'] = migration_utc
            for nest in nest_dict:
                for report in nest_dict[nest]['reports']:
                    self.bot.guild_dict[guild.id]['nest_dict'][channel.id][nest]['reports'][report]['exp'] = migration_utc.replace(tzinfo=datetime.timezone.utc).timestamp()
            confirmation = await channel.send(_('Migration time set.'))
            await asyncio.sleep(10)
            await confirmation.delete()
            return
        else:
            return

def setup(bot):
    bot.add_cog(Nest(bot))

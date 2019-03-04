import asyncio
import copy
import re

import discord
from discord.ext import commands
import time
from time import strftime

from meowth import utils
from meowth import checks
from meowth.exts import pokemon as pkmn_class

class Configure:
    def __init__(self, bot):
        self.bot = bot

    async def configure_city_channels(self, ctx, config_dict_temp, type, reply_options, output):
        guild = ctx.message.guild
        owner = ctx.message.author
        citychannel_dict = {}
        channels = None
        if config_dict_temp[type].get('report_channels'):
            if output == "list":
                channels = [ctx.bot.get_channel(x) for x in config_dict_temp[type]['report_channels']]
                channels = [x.name for x in channels if x]
            else:
                channels = [ctx.bot.get_channel(x) for x in config_dict_temp[type]['report_channels'].keys()]
                channels = [x.name for x in channels if x]
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Enabled: {config_dict_temp[type]['enabled']}\nChannels: {str(channels)}").set_author(name=_("Current {type} Setting").format(type=type.title()), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            citychannels = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if citychannels.content.lower() == 'n':
                config_dict_temp[type]['enabled'] = False
                if output == "list":
                    config_dict_temp[type]['report_channels'] = []
                else:
                    config_dict_temp[type]['report_channels'] = {}
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('{type} Reporting disabled').format(type=type.title())))
                config_dict_temp[type]['enabled'] = False
                return config_dict_temp
            elif citychannels.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                config_dict_temp[type]['enabled'] = True
                citychannel_list = citychannels.content.lower().split(',')
                citychannel_list = [x.strip() for x in citychannel_list]
                guild_channel_list = []
                for channel in guild.text_channels:
                    guild_channel_list.append(channel.id)
                citychannel_objs = []
                citychannel_names = []
                citychannel_errors = []
                for item in citychannel_list:
                    channel = None
                    if item.isdigit():
                        channel = discord.utils.get(guild.text_channels, id=int(item))
                    if not channel:
                        item = re.sub('[^a-zA-Z0-9 _\\-]+', '', item)
                        item = item.replace(" ", "-")
                        name = await utils.letter_case(guild.text_channels, item.lower())
                        channel = discord.utils.get(guild.text_channels, name=name)
                    if channel:
                        citychannel_objs.append(channel)
                        citychannel_names.append(channel.name)
                    else:
                        citychannel_errors.append(item)
                citychannel_list = [x.id for x in citychannel_objs]
                diff = set(citychannel_list) - set(guild_channel_list)
                if (not diff) and (not citychannel_errors):
                    await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('{type} Reporting Channels enabled').format(type=type.title())))
                    for channel in citychannel_objs:
                        ow = channel.overwrites_for(self.bot.user)
                        ow.send_messages = True
                        ow.read_messages = True
                        ow.manage_roles = True
                        try:
                            await channel.set_permissions(self.bot.user, overwrite = ow)
                        except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_('I couldn\'t set my own permissions in this channel. Please ensure I have the correct permissions in {channel} using **{prefix}get perms**.').format(prefix=ctx.prefix, channel=channel.mention)))
                    break
                else:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("The channel list you provided doesn't match with your servers channels.\n\nThe following aren't in your server: **{invalid_channels}**\n\nPlease double check your channel list and resend your reponse.").format(invalid_channels=', '.join(citychannel_errors))))
                    continue
        if output == "list":
            config_dict_temp[type]['report_channels'] = citychannel_list
            return config_dict_temp
        if config_dict_temp[type]['enabled']:
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_('For each report, I generate Google Maps links to give people directions to the raid or egg! To do this, I need to know which suburb/town/region each report channel represents, to ensure we get the right location in the map. For each report channel you provided, I will need its corresponding general location using only letters and spaces, with each location seperated by a comma and space.\n\nExample: `kansas city mo, hull uk, sydney nsw australia`\n\nEach location will have to be in the same order as you provided the channels in the previous question.\n\nRespond with: **location info, location info, location info** each matching the order of the previous channel list below.')).set_author(name=_('{type} Reporting Locations').format(type=type.title()), icon_url=self.bot.user.avatar_url))
            channels = ""
            if config_dict_temp[type]['report_channels']:
                channels = {ctx.bot.get_channel(k):v for k,v in config_dict_temp[type]['report_channels'].items()}
                channels = {k.name:v for k,v in channels.items() if k}
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"{channels}\n\n**You Entered**:\n{citychannel_names}").set_author(name=_("Current Report Locations"), icon_url=self.bot.user.avatar_url), delete_after=300)
            while True:
                cities = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
                if cities.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                    return None
                city_list = cities.content.split(',')
                city_list = [x.strip() for x in city_list]
                if len(city_list) == len(citychannel_list):
                    for i in range(len(citychannel_list)):
                        citychannel_dict[citychannel_list[i]] = city_list[i]
                    break
                else:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("The number of cities doesn't match the number of channels you gave me earlier!\n\nI'll show you the two lists to compare:\n\n{channellist}\n{citylist}\n\nPlease double check that your locations match up with your provided channels and resend your response.").format(channellist=', '.join(citychannel_names), citylist=', '.join(city_list))))
                    continue
            config_dict_temp[type]['report_channels'] = citychannel_dict
            await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('{type} Reporting Locations are set').format(type=type.title())))
            if output == "dict":
                return config_dict_temp
            if type == "raid":
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("How would you like me to categorize the raid channels I create? Your options are:\n\n**none** - If you don't want them categorized\n**same** - If you want them in the same category as the reporting channel\n**region** - If you want them categorized by region\n**level** - If you want them categorized by level.")).set_author(name=_('Raid Reporting Categories'), icon_url=self.bot.user.avatar_url))
            elif type == "exraid":
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("How would you like me to categorize the EX raid channels I create? Your options are:\n\n**none** - If you don't want them categorized\n**same** - If you want them in the same category as the reporting channel\n**other** - If you want them categorized in a provided category name or ID")).set_author(name=_('EX Raid Reporting Categories'), icon_url=self.bot.user.avatar_url))
            elif type == "meetup":
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("How would you like me to categorize the meetup channels I create? Your options are:\n\n**none** - If you don't want them categorized\n**same** - If you want them in the same category as the reporting channel\n**other** - If you want them categorized in a provided category name or ID")).set_author(name=_('Meetup Reporting Categories'), icon_url=self.bot.user.avatar_url))
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp[type]['categories'])).set_author(name=_("Current Category Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
            while True:
                guild = self.bot.get_guild(guild.id)
                guild_catlist = []
                for cat in guild.categories:
                    guild_catlist.append(cat.id)
                category_dict = {}
                categories = await self.bot.wait_for('message', check=lambda message: message.guild == None and message.author == owner)
                if categories.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                    return None
                elif categories.content.lower() == 'none' and categories.content.lower() in reply_options:
                    config_dict_temp[type]['categories'] = None
                    break
                elif categories.content.lower() == 'same' and categories.content.lower() in reply_options:
                    config_dict_temp[type]['categories'] = 'same'
                    break
                elif categories.content.lower() == 'region' and categories.content.lower() in reply_options:
                    while True:
                        guild = self.bot.get_guild(guild.id)
                        guild_catlist = []
                        for cat in guild.categories:
                            guild_catlist.append(cat.id)
                        config_dict_temp[type]['categories'] = 'region'
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("In the same order as they appear below, please give the names of the categories you would like raids reported in each channel to appear in. You do not need to use different categories for each channel, but they do need to be pre-existing categories. Separate each category name with a comma. Response can be either category name or ID.\n\nExample: `kansas city, hull, 1231231241561337813`\n\nYou have configured the following channels as raid reporting channels.")).set_author(name=_('{type} Reporting Categories').format(type=type.title()), icon_url=self.bot.user.avatar_url))
                        channels = ""
                        if config_dict_temp[type]['category_dict']:
                            channels = {ctx.bot.get_channel(k):ctx.bot.get_channel(v) for k,v in config_dict_temp[type]['category_dict'].items()}
                            channels = {k.name:v.name for k,v in channels.items() if k}
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"{channels}\n\n**You Entered**:\n{citychannel_names}").set_author(name=_("Current Report Categories"), icon_url=self.bot.user.avatar_url), delete_after=300)
                        regioncats = await self.bot.wait_for('message', check=lambda message: message.guild == None and message.author == owner)
                        if regioncats.content.lower() == "cancel":
                            await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                            return None
                        regioncat_list = regioncats.content.split(',')
                        regioncat_list = [x.strip() for x in regioncat_list]
                        regioncat_ids = []
                        regioncat_names = []
                        regioncat_errors = []
                        for item in regioncat_list:
                            category = None
                            if item.isdigit():
                                category = discord.utils.get(guild.categories, id=int(item))
                            if not category:
                                name = await utils.letter_case(guild.categories, item.lower())
                                category = discord.utils.get(guild.categories, name=name)
                            if category:
                                regioncat_ids.append(category.id)
                                regioncat_names.append(category.name)
                            else:
                                regioncat_errors.append(item)
                        regioncat_list = regioncat_ids
                        if len(regioncat_list) == len(citychannel_list):
                            catdiff = set(regioncat_list) - set(guild_catlist)
                            if (not catdiff) and (not regioncat_errors):
                                for i in range(len(citychannel_list)):
                                    category_dict[citychannel_list[i]] = regioncat_list[i]
                                break
                            else:
                                msg = _("The category list you provided doesn't match with your server's categories.")
                                if regioncat_errors:
                                    msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(regioncat_errors))
                                msg += _("\n\nPlease double check your category list and resend your response. If you just made these categories, try again.")
                                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                                continue
                        else:
                            msg = _("The number of categories I found in your server doesn't match the number of channels you gave me earlier!\n\nI'll show you the two lists to compare:\n\n**Matched Channels:** {channellist}\n**Matched Categories:** {catlist}\n\nPlease double check that your categories match up with your provided channels and resend your response.").format(channellist=', '.join(citychannel_names), catlist=', '.join(regioncat_names) if len(regioncat_list)>0 else "None")
                            if regioncat_errors:
                                msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(regioncat_errors))
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                            continue
                        break
                elif categories.content.lower() == 'level' and categories.content.lower() in reply_options:
                    config_dict_temp[type]['categories'] = 'level'
                    while True:
                        guild = self.bot.get_guild(guild.id)
                        guild_catlist = []
                        for cat in guild.categories:
                            guild_catlist.append(cat.id)
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Pokemon Go currently has five levels of raids. Please provide the names of the categories you would like each level of raid to appear in. Use the following order: 1, 2, 3, 4, 5 \n\nYou do not need to use different categories for each level, but they do need to be pre-existing categories. Separate each category name with a comma. Response can be either category name or ID.\n\nExample: `level 1-3, level 1-3, level 1-3, level 4, 1231231241561337813`")).set_author(name=_('{type} Reporting Categories').format(type=type.title()), icon_url=self.bot.user.avatar_url))
                        channels = ""
                        if config_dict_temp[type]['category_dict']:
                            channels = {k:ctx.bot.get_channel(v) for k,v in config_dict_temp[type]['category_dict'].items()}
                            channels = {k:v.name for k,v in channels.items() if k}
                            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"{channels}").set_author(name=_("Current Report Categories"), icon_url=self.bot.user.avatar_url), delete_after=300)
                        levelcats = await self.bot.wait_for('message', check=lambda message: message.guild == None and message.author == owner)
                        if levelcats.content.lower() == "cancel":
                            await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                            return None
                        levelcat_list = levelcats.content.split(',')
                        levelcat_list = [x.strip() for x in levelcat_list]
                        levelcat_ids = []
                        levelcat_names = []
                        levelcat_errors = []
                        for item in levelcat_list:
                            category = None
                            if item.isdigit():
                                category = discord.utils.get(guild.categories, id=int(item))
                            if not category:
                                name = await utils.letter_case(guild.categories, item.lower())
                                category = discord.utils.get(guild.categories, name=name)
                            if category:
                                levelcat_ids.append(category.id)
                                levelcat_names.append(category.name)
                            else:
                                levelcat_errors.append(item)
                        levelcat_list = levelcat_ids
                        if len(levelcat_list) == 5:
                            catdiff = set(levelcat_list) - set(guild_catlist)
                            if (not catdiff) and (not levelcat_errors):
                                level_list = ["1", '2', '3', '4', '5']
                                for i in range(5):
                                    category_dict[level_list[i]] = levelcat_list[i]
                                break
                            else:
                                msg = _("The category list you provided doesn't match with your server's categories.")
                                if levelcat_errors:
                                    msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(levelcat_errors))
                                msg += _("\n\nPlease double check your category list and resend your response. If you just made these categories, try again.")
                                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                                continue
                        else:
                            msg = _("The number of categories I found in your server doesn't match the number of raid levels! Make sure you give me exactly six categories, one for each level of raid. You can use the same category for multiple levels if you want, but I need to see five category names.\n\n**Matched Categories:** {catlist}\n\nPlease double check your categories.").format(catlist=', '.join(levelcat_names) if len(levelcat_list)>0 else "None")
                            if levelcat_errors:
                                msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(levelcat_errors))
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                            continue
                elif categories.content.lower() == 'other' and categories.content.lower() in reply_options:
                    while True:
                        guild = self.bot.get_guild(guild.id)
                        guild_catlist = []
                        for cat in guild.categories:
                            guild_catlist.append(cat.id)
                        config_dict_temp[type]['categories'] = 'region'
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("In the same order as they appear below, please give the names of the categories you would like raids reported in each channel to appear in. You do not need to use different categories for each channel, but they do need to be pre-existing categories. Separate each category name with a comma. Response can be either category name or ID.\n\nExample: `kansas city, hull, 1231231241561337813`\n\nYou have configured the following channels as reporting channels.")).set_author(name=_('{type} Reporting Categories').format(type=type.title()), icon_url=self.bot.user.avatar_url))
                        channels = ""
                        if config_dict_temp[type]['category_dict']:
                            channels = {ctx.bot.get_channel(k):ctx.bot.get_channel(v) for k,v in config_dict_temp[type]['category_dict'].items()}
                            channels = {k.name:v.name for k,v in channels.items() if k}
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"{channels}\n\n**You Entered**:\n{citychannel_names}").set_author(name=_("Current Report Categories"), icon_url=self.bot.user.avatar_url), delete_after=300)
                        regioncats = await self.bot.wait_for('message', check=lambda message: message.guild == None and message.author == owner)
                        if regioncats.content.lower() == "cancel":
                            await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                            return None
                        regioncat_list = regioncats.content.split(',')
                        regioncat_list = [x.strip() for x in regioncat_list]
                        regioncat_ids = []
                        regioncat_names = []
                        regioncat_errors = []
                        for item in regioncat_list:
                            category = None
                            if item.isdigit():
                                category = discord.utils.get(guild.categories, id=int(item))
                            if not category:
                                name = await utils.letter_case(guild.categories, item.lower())
                                category = discord.utils.get(guild.categories, name=name)
                            if category:
                                regioncat_ids.append(category.id)
                                regioncat_names.append(category.name)
                            else:
                                regioncat_errors.append(item)
                        regioncat_list = regioncat_ids
                        if len(regioncat_list) == len(citychannel_list):
                            catdiff = set(regioncat_list) - set(guild_catlist)
                            if (not catdiff) and (not regioncat_errors):
                                for i in range(len(citychannel_list)):
                                    category_dict[citychannel_list[i]] = regioncat_list[i]
                                break
                            else:
                                msg = _("The category list you provided doesn't match with your server's categories.")
                                if regioncat_errors:
                                    msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(regioncat_errors))
                                msg += _("\n\nPlease double check your category list and resend your response. If you just made these categories, try again.")
                                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                                continue
                        else:
                            msg = _("The number of categories I found in your server doesn't match the number of channels you gave me earlier!\n\nI'll show you the two lists to compare:\n\n**Matched Channels:** {channellist}\n**Matched Categories:** {catlist}\n\nPlease double check that your categories match up with your provided channels and resend your response.").format(channellist=', '.join(citychannel_names), catlist=', '.join(regioncat_names) if len(regioncat_list)>0 else "None")
                            if regioncat_errors:
                                msg += _("\n\nThe following aren't in your server: **{invalid_categories}**").format(invalid_categories=', '.join(regioncat_errors))
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=msg))
                            continue
                        break
                else:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Sorry, I didn't understand your answer! Try again.")))
                    continue
                break
            await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('{type} Categories are set').format(type=type.title())))
            config_dict_temp[type]['category_dict'] = category_dict
            return config_dict_temp

    @commands.group(case_insensitive=True, invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def configure(self, ctx, *, configlist: str=""):
        """Meowth Configuration

        Usage: !configure [list]
        Meowth will DM you instructions on how to configure Meowth for your server.
        If it is not your first time configuring, you can choose a section to jump to.
        You can also include a comma separated [list] of sections from the following:
        all, team, welcome, raid, exraid, invite, counters, wild, research, want, archive, timezone"""
        await self._configure(ctx, configlist)

    async def _configure(self, ctx, configlist):
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        for session in self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].keys():
            if not guild.get_member(session):
                try:
                    del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][session]
                except KeyError:
                    pass
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        firstconfig = False
        all_commands = [str(x) for x in config_dict_temp.keys()]
        enabled_commands = []
        configreplylist = []
        config_error = False
        if not config_dict_temp['settings']['done']:
            firstconfig = True
        if configlist and not firstconfig:
            configlist = configlist.lower().replace("timezone", "settings").split(",")
            configlist = [x.strip().lower() for x in configlist]
            diff =  set(configlist) - set(all_commands)
            if diff and "all" in diff:
                configreplylist = all_commands
            elif not diff:
                configreplylist = configlist
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry, I couldn't understand some of what you entered. Let's just start here.")))
        if config_dict_temp['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(config_dict_temp['settings']['config_sessions'].values()), yoursessions=config_dict_temp['settings']['config_sessions'][owner.id])))
        configmessage = _("Meowth! That's Right! Welcome to the configuration for Meowth the Pokemon Go Helper Bot! I will be guiding you through some steps to get me setup on your server.\n\n**Role Setup**\nBefore you begin the configuration, please make sure my role is moved to the top end of the server role hierarchy. It can be under admins and mods, but must be above team and general roles. [Here is an example](http://i.imgur.com/c5eaX1u.png)")
        if not firstconfig and not configreplylist:
            configmessage += _("\n\n**Welcome Back**\nThis isn't your first time configuring. You can either reconfigure everything by replying with **all** or reply with a comma separated list to configure those commands. Example: `want, raid, wild`")
            for commandconfig in config_dict_temp.keys():
                if config_dict_temp[commandconfig].get('enabled', False):
                    enabled_commands.append(commandconfig)
            configmessage += _("\n\n**Enabled Commands:**\n{enabled_commands}").format(enabled_commands=", ".join(enabled_commands))
            configmessage += _("\n\n**All Commands:**\n**all** - To redo configuration\n**team** - For Team Assignment configuration\n**welcome** - For Welcome Message configuration\n**raid** - for raid command configuration\n**exraid** - for EX raid command configuration\n**invite** - for invite command configuration\n**counters** - for automatic counters configuration\n**wild** - for wild command configuration\n**research** - for !research command configuration\n**meetup** - for !meetup command configuration\n**want** - for want/unwant command configuration\n**archive** - For !archive configuration\n**trade** - For trade command configuration\n**nest** - For nest command configuration\n**timezone** - For timezone configuration\n**scanners** - For scanner bot integration configuration")
            configmessage += _('\n\nReply with **cancel** at any time throughout the questions to cancel the configure process.')
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=configmessage).set_author(name=_('Meowth Configuration - {guild}').format(guild=guild.name), icon_url=self.bot.user.avatar_url))
            while True:
                def check(m):
                    return m.guild == None and m.author == owner
                configreply = await self.bot.wait_for('message', check=check)
                configreply.content = configreply.content.replace("timezone", "settings")
                if configreply.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                    try:
                        del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
                    except KeyError:
                        pass
                    return None
                elif "all" in configreply.content.lower():
                    configreplylist = all_commands
                    break
                else:
                    configreplylist = configreply.content.lower().split(",")
                    configreplylist = [x.strip() for x in configreplylist]
                    for configreplyitem in configreplylist:
                        if configreplyitem not in all_commands:
                            config_error = True
                            break
                if config_error:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with the choices above.")))
                    continue
                else:
                    break
        elif firstconfig == True:
            configmessage += _('\n\nReply with **cancel** at any time throughout the questions to cancel the configure process.')
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=configmessage).set_author(name=_('Meowth Configuration - {guild}').format(guild=guild.name), icon_url=self.bot.user.avatar_url))
            configreplylist = all_commands
        try:
            if "team" in configreplylist:
                ctx = await self._configure_team(ctx)
                if not ctx:
                    return None
            if "welcome" in configreplylist:
                ctx = await self._configure_welcome(ctx)
                if not ctx:
                    return None
            if "raid" in configreplylist:
                ctx = await self._configure_raid(ctx)
                if not ctx:
                    return None
            if "exraid" in configreplylist:
                ctx = await self._configure_exraid(ctx)
                if not ctx:
                    return None
            if "meetup" in configreplylist:
                ctx = await self._configure_meetup(ctx)
                if not ctx:
                    return None
            if "invite" in configreplylist:
                ctx = await self._configure_invite(ctx)
                if not ctx:
                    return None
            if "counters" in configreplylist:
                ctx = await self._configure_counters(ctx)
                if not ctx:
                    return None
            if "archive" in configreplylist:
                ctx = await self._configure_archive(ctx)
                if not ctx:
                    return None
            if "wild" in configreplylist:
                ctx = await self._configure_wild(ctx)
                if not ctx:
                    return None
            if "research" in configreplylist:
                ctx = await self._configure_research(ctx)
                if not ctx:
                    return None
            if "want" in configreplylist:
                ctx = await self._configure_want(ctx)
                if not ctx:
                    return None
            if "trade" in configreplylist:
                ctx = await self._configure_trade(ctx)
                if not ctx:
                    return None
            if "nest" in configreplylist:
                ctx = await self._configure_nest(ctx)
                if not ctx:
                    return None
            if "settings" in configreplylist:
                ctx = await self._configure_settings(ctx)
                if not ctx:
                    return None
            if "scanners" in configreplylist:
                ctx = await self._configure_scanners(ctx)
                if not ctx:
                    return None
        finally:
            if ctx:
                ctx.config_dict_temp['settings']['done'] = True
                self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
            try:
                del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
            except KeyError:
                pass

    @configure.command(name='all')
    async def configure_all(self, ctx):
        """All settings"""
        await self._configure(ctx, "all")

    @configure.command()
    async def team(self, ctx):
        """!team command settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_team(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_team(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Team assignment allows users to assign their Pokemon Go team role using the **!team** command. If you have a bot that handles this already, you may want to disable this feature.\n\nIf you are to use this feature, ensure existing team roles are as follows: mystic, valor, instinct. These must be all lowercase letters. If they don't exist yet, I'll make some for you instead.\n\nRespond here with: **N** to disable, **Y** to enable:")).set_author(name=_('Team Assignments'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['team']['enabled'])).set_author(name=_("Current Team Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            teamreply = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if teamreply.content.lower() == 'y':
                config_dict_temp['team']['enabled'] = True
                team_list = ["mystic", "valor", "instinct", "harmony"]
                team_colors = [discord.Colour.blue(), discord.Colour.red(), discord.Colour.gold(), discord.Colour.default()]
                team_roles = []
                team_dict = {}
                index = 0
                role_error = False
                role_create = ""
                while True:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Please respond with the names or IDs for the roles you would like to use for teams in the following order:\n\n**mystic, valor, instinct, harmony**\n\nIf I can't find a role, I'll make a temporary role for you that you can either keep and rename, or you can delete and attempt to configure roles again.")).set_author(name=_('Team Assignments'), icon_url=self.bot.user.avatar_url))
                    if config_dict_temp['team']['team_roles']:
                        roles = {k:guild.get_role(v) for k,v in config_dict_temp['team']['team_roles'].items()}
                        roles = {k:v.name for k,v in roles.items() if v}
                        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"{roles}").set_author(name=_("Current Team Roles"), icon_url=self.bot.user.avatar_url), delete_after=300)
                    def check(m):
                        return m.guild == None and m.author == owner
                    rolesreply = await self.bot.wait_for('message', check=check)
                    if rolesreply.content.lower() == 'cancel':
                        await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                        return None
                    else:
                        rolesreplylist = rolesreply.content.split(",")
                        rolesreplylist = [x.strip() for x in rolesreplylist]
                        if len(rolesreplylist) == 4:
                            for item in rolesreplylist:
                                role = None
                                if item.isdigit():
                                    role = discord.utils.get(guild.roles, id=int(item))
                                if not role:
                                    name = await utils.letter_case(guild.roles, item.lower())
                                    role = discord.utils.get(guild.roles, name=name)
                                if not role:
                                    try:
                                        role = await guild.create_role(name=f"Meowth{team_list[index].capitalize()}", hoist=False, mentionable=True, colour=team_colors[index])
                                        role_create += _("I couldn\'t find role **{item}**. I created a role called **{meowthrole}** for team {team} in its place, you can rename it or delete it in Server Settings and try again later.\n\n").format(item=item, meowthrole=role.name, team=team_list[index].capitalize())
                                    except discord.errors.HTTPException:
                                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Maximum guild roles reached, delete some and try again.")))
                                    except (discord.errors.Forbidden, discord.errors.InvalidArgument):
                                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I can\'t create roles! Try again when ready.")))
                                if role:
                                    team_roles.append(role.id)
                                else:
                                    role_error = True
                                    break
                                index += 1
                            if role_create:
                                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=role_create))
                            if role_error:
                                continue
                            else:
                                for i in range(len(team_roles)):
                                    team_dict[team_list[i]] = team_roles[i]
                                break
                        else:
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I need you to enter four roles, one for each team and a role for no-team / harmony")))
                            continue
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_("Team roles set")))
                config_dict_temp['team']['team_roles'] = team_dict
                break
            elif teamreply.content.lower() == 'n':
                config_dict_temp['team']['enabled'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Team Assignments disabled!')))
                break
            elif teamreply.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable.")))
                continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def welcome(self, ctx):
        """Welcome message settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_welcome(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_welcome(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        welcomeconfig = _('I can welcome new members to the server with a short message. Here is an example, but it is customizable:\n\n')
        if config_dict_temp['team']['enabled']:
            welcomeconfig += _("Meowth! Welcome to {server_name}, {owner_name.mention}! Set your team by typing '**!team mystic**' or '**!team valor**' or '**!team instinct**' without quotations. If you have any questions just ask an admin.").format(server_name=guild.name, owner_name=owner)
        else:
            welcomeconfig += _('Meowth! Welcome to {server_name}, {owner_name.mention}! If you have any questions just ask an admin.').format(server_name=guild, owner_name=owner)
        welcomeconfig += _('\n\nThis welcome message can be in a specific channel or a direct message. If you have a bot that handles this already, you may want to disable this feature.\n\nRespond with: **N** to disable, **Y** to enable:')
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=welcomeconfig).set_author(name=_('Welcome Message'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['welcome']['enabled'])).set_author(name=_("Current Welcome Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            welcomereply = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if welcomereply.content.lower() == 'y':
                config_dict_temp['welcome']['enabled'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Welcome Message enabled!')))
                await owner.send(embed=discord.Embed(
                    colour=discord.Colour.lighter_grey(),
                    description=(_("Would you like a custom welcome message? "
                                 "You can reply with **N** to use the default message above or enter your own below.\n\n"
                                 "I can read all [discord formatting](https://support.discordapp.com/hc/en-us/articles/210298617-Markdown-Text-101-Chat-Formatting-Bold-Italic-Underline-) "
                                 "and I have the following template tags:\n\n"
                                 "**{@member}** - Replace member with user name or ID\n"
                                 "**{#channel}** - Replace channel with channel name or ID\n"
                                 "**{&role}** - Replace role name or ID (shows as @deleted-role DM preview)\n"
                                 "**{user}** - Will mention the new user\n"
                                 "**{server}** - Will print your server's name\n"
                                 "Surround your message with [] to send it as an embed. **Warning:** Mentions within embeds may be broken on mobile, this is a Discord bug."))).set_author(name=_("Welcome Message"), icon_url=self.bot.user.avatar_url))
                if config_dict_temp['welcome'].get('welcomemsg', 'default') != 'default':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['welcome']['welcomemsg'])).set_author(name=_("Current Welcome Message"), icon_url=self.bot.user.avatar_url), delete_after=300)
                while True:
                    welcomemsgreply = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and (message.author == owner)))
                    if welcomemsgreply.content.lower() == 'n':
                        config_dict_temp['welcome']['welcomemsg'] = 'default'
                        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_("Default welcome message set")))
                        break
                    elif welcomemsgreply.content.lower() == "cancel":
                        await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_("**CONFIG CANCELLED!**\n\nNo changes have been made.")))
                        return None
                    elif len(welcomemsgreply.content) > 500:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Please shorten your message to less than 500 characters. You entered {count}.").format(count=len(welcomemsgreply.content))))
                        continue
                    else:
                        welcomemessage, errors = utils.do_template(welcomemsgreply.content, owner, guild)
                        if errors:
                            if welcomemessage.startswith("[") and welcomemessage.endswith("]"):
                                embed = discord.Embed(colour=guild.me.colour, description=welcomemessage[1:-1].format(user=owner.mention))
                                embed.add_field(name=_('Warning'), value=_('The following could not be found:\n{}').format('\n'.join(errors)))
                                await owner.send(embed=embed)
                            else:
                                await owner.send(_("{msg}\n\n**Warning:**\nThe following could not be found: {errors}").format(msg=welcomemessage, errors=', '.join(errors)))
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Please check the data given and retry a new welcome message, or reply with **N** to use the default.")))
                            continue
                        else:
                            if welcomemessage.startswith("[") and welcomemessage.endswith("]"):
                                embed = discord.Embed(colour=guild.me.colour, description=welcomemessage[1:-1].format(user=owner.mention))
                                question = await owner.send(content=_("Here's what you sent. Does it look ok?"), embed=embed)
                                try:
                                    timeout = False
                                    res, reactuser = await utils.ask(self.bot, question, owner.id)
                                except TypeError:
                                    timeout = True
                            else:
                                question = await owner.send(content=_("Here's what you sent. Does it look ok?\n\n{welcome}").format(welcome=welcomemessage.format(user=owner.mention)))
                                try:
                                    timeout = False
                                    res, reactuser = await utils.ask(self.bot, question, owner.id)
                                except TypeError:
                                    timeout = True
                        if timeout or res.emoji == '❎':
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Please enter a new welcome message, or reply with **N** to use the default.")))
                            continue
                        else:
                            config_dict_temp['welcome']['welcomemsg'] = welcomemessage
                            await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_("Welcome Message set to:\n\n{}").format(config_dict_temp['welcome']['welcomemsg'])))
                            break
                    break
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Which channel in your server would you like me to post the Welcome Messages? You can also choose to have them sent to the new member via Direct Message (DM) instead.\n\nRespond with: **channel-name** or ID of a channel in your server or **DM** to Direct Message:")).set_author(name=_("Welcome Message Channel"), icon_url=self.bot.user.avatar_url))
                if config_dict_temp['welcome']['welcomechan']:
                    if config_dict_temp['welcome']['welcomechan'] == "dm":
                        channel = "DM"
                    else:
                        channel = ctx.bot.get_channel(config_dict_temp['welcome']['welcomechan'])
                        channel = channel.name
                    await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=channel).set_author(name=_("Current Welcome Channel"), icon_url=self.bot.user.avatar_url), delete_after=300)
                while True:
                    welcomechannelreply = await self.bot.wait_for('message', check=lambda message: message.guild == None and message.author == owner)
                    if welcomechannelreply.content.lower() == "dm":
                        config_dict_temp['welcome']['welcomechan'] = "dm"
                        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_("Welcome DM set")))
                        break
                    elif " " in welcomechannelreply.content.lower():
                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Channel names can't contain spaces, sorry. Please double check the name and send your response again.")))
                        continue
                    elif welcomechannelreply.content.lower() == "cancel":
                        await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                        return None
                    else:
                        item = welcomechannelreply.content
                        channel = None
                        if item.isdigit():
                            channel = discord.utils.get(guild.text_channels, id=int(item))
                        if not channel:
                            item = re.sub('[^a-zA-Z0-9 _\\-]+', '', item)
                            item = item.replace(" ", "-")
                            name = await utils.letter_case(guild.text_channels, item.lower())
                            channel = discord.utils.get(guild.text_channels, name=name)
                        if channel:
                            guild_channel_list = []
                            for textchannel in guild.text_channels:
                                guild_channel_list.append(textchannel.id)
                            diff = set([channel.id]) - set(guild_channel_list)
                        else:
                            diff = True
                        if (not diff):
                            config_dict_temp['welcome']['welcomechan'] = channel.id
                            ow = channel.overwrites_for(self.bot.user)
                            ow.send_messages = True
                            ow.read_messages = True
                            ow.manage_roles = True
                            try:
                                await channel.set_permissions(self.bot.user, overwrite = ow)
                            except (discord.errors.Forbidden, discord.errors.HTTPException, discord.errors.InvalidArgument):
                                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_('I couldn\'t set my own permissions in this channel. Please ensure I have the correct permissions in {channel} using **{prefix}get perms**.').format(prefix=ctx.prefix, channel=channel.mention)))
                            await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Welcome Channel set to {channel}').format(channel=welcomechannelreply.content.lower())))
                            break
                        else:
                            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("The channel you provided isn't in your server. Please double check your channel and resend your response.")))
                            continue
                    break
                break
            elif welcomereply.content.lower() == 'n':
                config_dict_temp['welcome']['enabled'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Welcome Message disabled!')))
                break
            elif welcomereply.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable.")))
                continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def raid(self, ctx):
        """!raid reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_raid(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_raid(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Raid cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Raid Reporting allows users to report active raids with **!raid** or raid eggs with **!raidegg**. Pokemon raid reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nExample: `kansas-city-raids, hull-raids, sydney-raids`\n\nIf you do not require raid or raid egg reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:")).set_author(name=_('Raid Reporting Channels'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "raid", ["none", "same", "region", "level"], output="category_dict")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def exraid(self, ctx):
        """!exraid reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_exraid(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_exraid(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Exraid cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("EX Raid Reporting allows users to report EX raids with **!exraid**. Pokemon EX raid reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nExample: `kansas-city-raids, hull-raids, sydney-raids`\n\nIf you do not require EX raid reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:")).set_author(name=_('EX Raid Reporting Channels'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "exraid", ["none", "same", "other"], output="category_dict")
        if not config_dict_temp:
            return None
        if config_dict_temp['exraid']['enabled']:
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Who do you want to be able to **see** the EX Raid channels? Your options are:\n\n**everyone** - To have everyone be able to see all reported EX Raids\n**same** - To only allow those with access to the reporting channel.")).set_author(name=_('EX Raid Channel Read Permissions'), icon_url=self.bot.user.avatar_url))
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['exraid']['permissions'])).set_author(name=_("Current Exraid Permissions"), icon_url=self.bot.user.avatar_url), delete_after=300)
            while True:
                permsconfigset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
                if permsconfigset.content.lower() == 'everyone':
                    config_dict_temp['exraid']['permissions'] = "everyone"
                    await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Everyone permission enabled')))
                    break
                elif permsconfigset.content.lower() == 'same':
                    config_dict_temp['exraid']['permissions'] = "same"
                    await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Same permission enabled')))
                    break
                elif permsconfigset.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                    return None
                else:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable.")))
                    continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def invite(self, ctx):
        """!invite command settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_invite(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_invite(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Invite cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        if not config_dict_temp['exraid']['enabled']:
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_('Do you want access to EX raids controlled through members using the **!invite** command?\nIf enabled, members will have read-only permissions for all EX Raids until they use **!invite** to gain access. If disabled, EX Raids will inherit the permissions from their reporting channels.\n\nRespond with: **N** to disable, or **Y** to enable:')).set_author(name=_('Invite Configuration'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['invite']['enabled'])).set_author(name=_("Current Invite Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            inviteconfigset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if inviteconfigset.content.lower() == 'y':
                config_dict_temp['invite']['enabled'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Invite Command enabled')))
                break
            elif inviteconfigset.content.lower() == 'n':
                config_dict_temp['invite']['enabled'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Invite Command disabled')))
                break
            elif inviteconfigset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable.")))
                continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def counters(self, ctx):
        """Automatic counters settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        ctx = await self._configure_counters(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_counters(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Counters cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_('Do you want to generate an automatic counters list in newly created raid channels using PokeBattler?\nIf enabled, I will post a message containing the best counters for the raid boss in new raid channels. Users will still be able to use **!counters** to generate this list.\n\nRespond with: **N** to disable, or enable with a comma separated list of boss levels that you would like me to generate counters for. Example:`3, 4, 5, EX`')).set_author(name=_('Automatic Counters Configuration'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Enabled: {config_dict_temp['counters']['enabled']}\nLevels: {config_dict_temp['counters']['auto_levels']}").set_author(name=_("Current Counters Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            countersconfigset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if countersconfigset.content.lower() == 'n':
                config_dict_temp['counters']['enabled'] = False
                config_dict_temp['counters']['auto_levels'] = []
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Automatic Counters disabled')))
                break
            elif countersconfigset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                counterlevel_list = countersconfigset.content.lower().split(',')
                counterlevel_list = [x.strip() for x in counterlevel_list]
                counterlevels = []
                for level in counterlevel_list:
                    if level.isdigit() and (int(level) <= 5):
                        counterlevels.append(str(level))
                    elif level == "ex":
                        counterlevels.append("EX")
                if len(counterlevels) > 0:
                    config_dict_temp['counters']['enabled'] = True
                    config_dict_temp['counters']['auto_levels'] = counterlevels
                    await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Automatic Counter Levels set to: {levels}').format(levels=', '.join((str(x) for x in config_dict_temp['counters']['auto_levels'])))))
                    break
                else:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Please enter at least one level from 1 to EX separated by comma. Ex: `4, 5, EX` or **N** to turn off automatic counters.")))
                    continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def wild(self, ctx):
        """!wild reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_wild(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_wild(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        wild_cog = self.bot.cogs.get('Wild')
        if not wild_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Wild Cog is not loaded. Wild cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Wild Reporting allows users to report wild spawns with **!wild**. Pokemon **wild** reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nExample: `kansas-city-wilds, hull-wilds, sydney-wilds`\n\nIf you do not require **wild** reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:")).set_author(name=_('Wild Reporting Channels'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "wild", [], output="dict")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def research(self, ctx):
        """!research reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_research(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_research(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        research_cog = self.bot.cogs.get('Research')
        if not research_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Research Cog is not loaded. Research cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Research Reporting allows users to report field research with **!research**. Pokemon **research** reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nExample: `kansas-city-research, hull-research, sydney-research`\n\nIf you do not require **research** reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:")).set_author(name=_('Research Reporting Channels'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "research", [], output="dict")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command(aliases=['event'])
    async def meetup(self, ctx):
        """!meetup reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_meetup(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_meetup(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Meetup cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        config_dict_temp['meetup'] = {'enabled':False, 'report_channels': {}, 'categories':'same', 'catgory_dict':{}}
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meetup Reporting allows users to report meetups with **!meetup** or **!event**. Meetup reports are contained within one or more channels. Each channel will be able to represent different areas/communities. I'll need you to provide a list of channels in your server you will allow reports from in this format: `channel-name, channel-name, channel-name`\n\nExample: `kansas-city-meetups, hull-meetups, sydney-meetups`\n\nIf you do not require meetup reporting, you may want to disable this function.\n\nRespond with: **N** to disable, or the **channel-name** list to enable, each seperated with a comma and space:")).set_author(name=_('Meetup Reporting Channels'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "meetup", ["none", "same", "other"], output="category_dict")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def want(self, ctx):
        """!want/!unwant settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_want(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_want(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        want_cog = self.bot.cogs.get('Want')
        if not want_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Want Cog is not loaded. Want cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The **!want** and **!unwant** commands let you add or remove roles for Pokemon that will be mentioned in reports. This let you get notifications on the Pokemon you want to track. I just need to know what channels you want to allow people to manage their pokemon with the **!want** and **!unwant** command.\n\nIf you don't want to allow the management of tracked Pokemon roles, then you may want to disable this feature.\n\nRepond with: **N** to disable, or the **channel-name** list to enable, each seperated by a comma and space.")).set_author(name=_('Pokemon Notifications'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "want", [], output="list")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def archive(self, ctx):
        """Configure !archive command settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_archive(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_archive(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        raid_cog = self.bot.cogs.get('Raid')
        if not raid_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Raid Cog is not loaded. Archive cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The **!archive** command marks temporary raid channels for archival rather than deletion. This can be useful for investigating potential violations of your server's rules in these channels.\n\nIf you would like to disable this feature, reply with **N**. Otherwise send the category you would like me to place archived channels in. You can say **same** to keep them in the same category, or type the name or ID of a category in your server.")).set_author(name=_('Archive Configuration'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Enabled: {config_dict_temp['archive']['enabled']}\nCategory: {config_dict_temp['archive']['category']}").set_author(name=_("Current Archive Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            archivemsg = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if archivemsg.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            if archivemsg.content.lower() == 'same':
                config_dict_temp['archive']['category'] = 'same'
                config_dict_temp['archive']['enabled'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Archived channels will remain in the same category.')))
                break
            if archivemsg.content.lower() == 'n':
                config_dict_temp['archive']['enabled'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Archived Channels disabled.')))
                break
            else:
                item = archivemsg.content
                category = None
                if item.isdigit():
                    category = discord.utils.get(guild.categories, id=int(item))
                if not category:
                    name = await utils.letter_case(guild.categories, item.lower())
                    category = discord.utils.get(guild.categories, name=name)
                if not category:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I couldn't find the category you replied with! Please reply with **same** to leave archived channels in the same category, or give the name or ID of an existing category.")))
                    continue
                config_dict_temp['archive']['category'] = category.id
                config_dict_temp['archive']['enabled'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Archive category set.')))
                break
        if config_dict_temp['archive']['enabled']:
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("I can also listen in your raid channels for words or phrases that you want to trigger an automatic archival. For example, if discussion of spoofing is against your server rules, you might tell me to listen for the word 'spoofing'.\n\nReply with **none** to disable this feature, or reply with a comma separated list of phrases you want me to listen in raid channels for.")).set_author(name=_('Archive Configuration'), icon_url=self.bot.user.avatar_url))
            if config_dict_temp['archive'].get('list', []):
                await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['archive']['list'])).set_author(name=_("Current Archive Phrases"), icon_url=self.bot.user.avatar_url), delete_after=300)
            phrasemsg = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if phrasemsg.content.lower() == 'none':
                config_dict_temp['archive']['list'] = None
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('Phrase list disabled.')))
            elif phrasemsg.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                phrase_list = phrasemsg.content.lower().split(",")
                for i in range(len(phrase_list)):
                    phrase_list[i] = phrase_list[i].strip()
                config_dict_temp['archive']['list'] = phrase_list
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Archive Phrase list set.')))
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command(aliases=['settings'])
    async def timezone(self, ctx):
        """Configure timezone and other settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_settings(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_settings(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("There are a few settings available that are not within **!configure**. To set these, use **!set <setting>** in any channel to set that setting.\n\nThese include:\n**!set regional <name or number>** - To set a server's regional raid boss\n**!set prefix <prefix>** - To set my command prefix\n**!set timezone <offset>** - To set offset outside of **!configure**\n**!set silph <trainer>** - To set a trainer's SilphRoad card (usable by members)\n**!set pokebattler <ID>** - To set a trainer's pokebattler ID (usable by members)\n\nHowever, we can do your timezone now to help coordinate reports for you. For others, use the **!set** command.\n\nThe current 24-hr time UTC is {utctime}. How many hours off from that are you?\n\nRespond with: A number from **-12** to **12**:").format(utctime=strftime('%H:%M', time.gmtime()))).set_author(name=_('Timezone Configuration and Other Settings'), icon_url=self.bot.user.avatar_url))
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['settings']['offset'])).set_author(name=_("Current Timezone Offset"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            offsetmsg = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if offsetmsg.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description=_('**CONFIG CANCELLED!**\n\nNo changes have been made.')))
                return None
            else:
                try:
                    offset = float(offsetmsg.content)
                except ValueError:
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I couldn't convert your answer to an appropriate timezone!\n\nPlease double check what you sent me and resend a number strarting from **-12** to **12**.")))
                    continue
                if (not ((- 12) <= offset <= 14)):
                    await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("I couldn't convert your answer to an appropriate timezone!\n\nPlease double check what you sent me and resend a number strarting from **-12** to **12**.")))
                    continue
                else:
                    break
        config_dict_temp['settings']['offset'] = offset
        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Timezone set')))
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def trade(self, ctx):
        """!trade reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_trade(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_trade(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        trade_cog = self.bot.cogs.get('Trading')
        if not trade_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Trade Cog is not loaded. Trade cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The **!trade** command allows your users to organize and coordinate trades. This command requires at least one channel specifically for trades.\n\nIf you would like to disable this feature, reply with **N**. Otherwise, just send the names or IDs of the channels you want to allow the **!trade** command in, separated by commas.")).set_author(name=_('Trade Configuration'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "trade", [], output="list")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def nest(self, ctx):
        """!nest reporting settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        if self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id] > 1:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("**MULTIPLE SESSIONS!**\n\nIt looks like you have **{yoursessions}** active configure sessions. I recommend you send **cancel** first and then send your request again to avoid confusing me.\n\nYour Sessions: **{yoursessions}** | Total Sessions: **{allsessions}**").format(allsessions=sum(self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'].values()), yoursessions=self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id])))
        ctx = await self._configure_nest(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name=_('Configuration Complete'), icon_url=self.bot.user.avatar_url))
        try:
            del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]
        except KeyError:
            pass

    async def _configure_nest(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        nest_cog = self.bot.cogs.get('Nest')
        if not nest_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Nest Cog is not loaded. Nest cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("The **!nest** command allows your users to report nests. This command requires at least one channel specifically for nests.\n\nIf you would like to disable this feature, reply with **N**. Otherwise, just send the names or IDs of the channels you want to allow the **!nest** command in, separated by commas.")).set_author(name=_('Nest Configuration'), icon_url=self.bot.user.avatar_url))
        config_dict_temp = await self.configure_city_channels(ctx, config_dict_temp, "nest", [], output="list")
        if not config_dict_temp:
            return None
        ctx.config_dict_temp = config_dict_temp
        return ctx

    @configure.command()
    async def scanners(self, ctx):
        """Configure scanner settings"""
        guild = ctx.message.guild
        owner = ctx.message.author
        await utils.safe_delete(ctx.message)
        if not self.bot.guild_dict[guild.id]['configure_dict']['settings']['done']:
            await self._configure(ctx, "all")
            return
        config_sessions = self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings'].setdefault('config_sessions', {}).setdefault(owner.id, 0) + 1
        self.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['config_sessions'][owner.id] = config_sessions
        ctx = await self._configure_scanners(ctx)
        if ctx:
            self.bot.guild_dict[guild.id]['configure_dict'] = ctx.config_dict_temp
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=_("Meowth! Alright! Your settings have been saved and I'm ready to go! If you need to change any of these settings, just type **!configure** in your server again.")).set_author(name='Configuration Complete', icon_url=self.bot.user.avatar_url))
        del self.bot.guild_dict[guild.id]['configure_dict']['settings']['config_sessions'][owner.id]

    async def _configure_scanners(self, ctx):
        guild = ctx.message.guild
        owner = ctx.message.author
        config_dict_temp = getattr(ctx, 'config_dict_temp', copy.deepcopy(self.bot.guild_dict[guild.id]['configure_dict']))
        huntr_cog = self.bot.cogs.get('Huntr')
        if not huntr_cog:
            await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description=_("Huntr Cog is not loaded. Scanners cannot be configured.")))
            ctx.config_dict_temp = config_dict_temp
            return ctx
        scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description='Do you want automatic **!raid** reports using supported bots enabled?\n\nAny raid that a bot posts in a channel that Meowth also has access to will be converted to a **!raid** report. If enabled, there are more options available for configuring this setting.\n\nRespond with: **N** to disable, or **Y** to enable:').set_author(name='Automatic Raid Reports', icon_url=self.bot.user.avatar_url)
        scanner_embed.add_field(name=_('**Supported Bots:**'), value=_('GymHuntrBot, NovaBot, PokeAlarm'))
        scanner_embed.add_field(name=_('**NovaBot / PokeAlarm Syntax:**'), value=_('Content must include: `!raid <form> <pkmn>|<gym_name>|<time_left>|<lat>,<lng>|<quick_move> / <charge_move>`'))
        await owner.send(embed=scanner_embed)
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners']['autoraid'])).set_author(name=_("Current AutoRaid Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            autoraidset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if autoraidset.content.lower() == 'y':
                config_dict_temp['scanners']['autoraid'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description='Automatic Raid Reports enabled'))
                break
            elif autoraidset.content.lower() == 'n':
                config_dict_temp['scanners']['autoraid'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Raid Reports disabled'))
                break
            elif autoraidset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
        if config_dict_temp['scanners']['autoraid']:
            scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter the levels that you would like Meowth to create raid channels automatically for, separated by a comma. Any level not included will be a reformatted report and will allow users to react to create a channel. You can also enter '0' to reformat all reports with no automatic channels. Use both this configuration and the other bot's configuration to customize your needs. See below.").set_author(name='Automatic Raid Report Levels', icon_url=self.bot.user.avatar_url)
            scanner_embed.add_field(name=_('**GymhuntrBot:**'), value=_("For example: `3, 4, 5`\n\nIn this example, if **!level 1** for @GymHuntrBot is used, level 1 and 2 raids will have a re-stylized raid report with a @mention, but no channel will be created. However, all level 3+ raids will have a channel created."))
            scanner_embed.add_field(name=_('**NovaBot and PokeAlarm:**'), value=_("For example: `3, 4, 5`\n\nIn this example, only 3+ raids will auto reported. You can customize the other levels manually in your alarm settings. "))
            await owner.send(embed=scanner_embed)
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners']['raidlvls'])).set_author(name=_("Current AutoRaid Levels"), icon_url=self.bot.user.avatar_url), delete_after=300)
            raidlevel_list = []
            config_dict_temp['scanners']['raidlvls'] = []
            while True:
                raidlevels = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
                if raidlevels.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                    return None
                elif raidlevels.content.lower() == 'n':
                    config_dict_temp['scanners']['autoraid'] = False
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Raid Reports disabled'))
                    break
                else:
                    raidlevel_list = raidlevels.content.lower().split(',')
                    for level in raidlevel_list:
                        if level.strip().isdigit() and (int(level) <= 5):
                            config_dict_temp['scanners']['raidlvls'].append(int(level))
                    if len(config_dict_temp['scanners']['raidlvls']) > 0:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Automatic Raid Channel Levels set to: {levels}').format(levels=', '.join((str(x) for x in config_dict_temp['scanners']['raidlvls'])))))
                        break
                    else:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="Please enter at least one number from 1 to 5 separated by comma. Ex: `1, 2, 3`. Enter '0' to have all raids restyled without any automatic channels, or **N** to turn off automatic raids."))
                        continue
        scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description='Do you want automatic **!raidegg** reports using supported bots enabled?\n\nAny egg that a bot posts in a channel that Meowth also has access to will be converted to a **!raidegg** report. If enabled, there are more options available for configuring this setting.\n\nRespond with: **N** to disable, or **Y** to enable:').set_author(name='Automatic Egg Reports', icon_url=self.bot.user.avatar_url)
        scanner_embed.add_field(name=_('**Supported Bots:**'), value=_('GymHuntrBot, NovaBot, PokeAlarm'))
        scanner_embed.add_field(name=_('**NovaBot / PokeAlarm Syntax:**'), value=_('Content must include: `!raidegg <level>|<gym_name>|<time_left_start>|<lat>,<lng>`'))
        await owner.send(embed=scanner_embed)
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners']['autoegg'])).set_author(name=_("Current AutoEgg Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            autoeggset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if autoeggset.content.lower() == 'y':
                config_dict_temp['scanners']['autoegg'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description='Automatic Egg Reports enabled'))
                break
            elif autoeggset.content.lower() == 'n':
                config_dict_temp['scanners']['autoegg'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Egg Reports disabled'))
                break
            elif autoeggset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
        if config_dict_temp['scanners']['autoegg']:
            scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description="Please enter the levels that you would like Meowth to create egg channels automatically for, separated by a comma. Any level not included will be a reformatted report and will allow users to react to create a channel. You can also enter '0' to reformat all reports with no automatic channels. Use both this configuration and the other bot's configuration to customize your needs. See below.").set_author(name='Automatic Egg Report Levels', icon_url=self.bot.user.avatar_url)
            scanner_embed.add_field(name=_('**GymhuntrBot:**'), value=_("For example: `3, 4, 5`\n\nIn this example, if **!level 1** for @GymHuntrBot is used, level 1 and 2 eggs will have a re-stylized raid report with a @mention, but no channel will be created. However, all level 3+ eggs will have a channel created."))
            scanner_embed.add_field(name=_('**NovaBot and PokeAlarm:**'), value=_("For example: `3, 4, 5`\n\nIn this example, only 3+ raids will auto reported. You can customize the other levels manually in your alarm settings. "))
            await owner.send(embed=scanner_embed)
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners']['egglvls'])).set_author(name=_("Current AutoEgg Levels"), icon_url=self.bot.user.avatar_url), delete_after=300)
            egglevel_list = []
            config_dict_temp['scanners']['egglvls'] = []
            while True:
                egglevels = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
                if egglevels.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                    return None
                elif egglevels.content.lower() == 'n':
                    config_dict_temp['scanners']['autoegg'] = False
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Egg Reports disabled'))
                    break
                else:
                    egglevel_list = egglevels.content.lower().split(',')
                    for level in egglevel_list:
                        if level.strip().isdigit() and (int(level) <= 5):
                            config_dict_temp['scanners']['egglvls'].append(int(level))
                    if len(config_dict_temp['scanners']['egglvls']) > 0:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Automatic Egg Channel Levels set to: {levels}').format(levels=', '.join((str(x) for x in config_dict_temp['scanners']['egglvls'])))))
                        break
                    else:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="Please enter at least one number from 1 to 5 separated by comma. Ex: `1, 2, 3`. Enter '0' to have all raids restyled without any automatic channels, or **N** to turn off automatic eggs."))
                        continue
        scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description='Do you want automatic **!wild** reports using supported bots enabled?\n\nAny wild that a bot posts in a channel that Meowth also has access to will be converted to a **!wild** report.\n\nRespond with: **N** to disable, or **Y** to enable:').set_author(name='Automatic Wild Reports', icon_url=self.bot.user.avatar_url)
        scanner_embed.add_field(name=_('**Supported Bots:**'), value=_('GymHuntrBot, NovaBot, PokeAlarm'))
        scanner_embed.add_field(name=_('**NovaBot / PokeAlarm Syntax:**'), value=_('Content must include: `!wild <form> <pkmn>|<lat>,<lng>|<time_left>|Weather: <weather> / IV: <iv>`'))
        await owner.send(embed=scanner_embed)
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners'].get('autowild', False))).set_author(name=_("Current AutoWild Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            wildconfigset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if wildconfigset.content.lower() == 'y':
                config_dict_temp['scanners']['autowild'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description='Automatic Wild Reports enabled'))
                break
            elif wildconfigset.content.lower() == 'n':
                config_dict_temp['scanners']['autowild'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Wild Reports disabled'))
                break
            elif wildconfigset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
        if config_dict_temp['scanners']['autowild']:
            scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description="If you don't have direct control over your reporting bot, you may want to blacklist some of its reports. Please enter a list of wild pokemon to block automatic reports of or reply with **N** to disable the fitler.").set_author(name='Automatic Wild Report Filter', icon_url=self.bot.user.avatar_url)
            await owner.send(embed=scanner_embed)
            await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners']['wildfilter'])).set_author(name=_("Current AutoWild Filter"), icon_url=self.bot.user.avatar_url), delete_after=300)
            wildfilter_list = []
            wildfilter_names = []
            config_dict_temp['scanners']['wildfilter'] = []
            while True:
                wildfilters = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
                if wildfilters.content.lower() == 'cancel':
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                    return None
                elif wildfilters.content.lower() == 'n':
                    config_dict_temp['scanners']['wildfilter'] = []
                    await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Wild filter disabled'))
                    break
                else:
                    wildfilter_list = wildfilters.content.lower().split(',')
                    for pkmn in wildfilter_list:
                        pokemon = pkmn_class.Pokemon.get_pokemon(ctx.bot, pkmn)
                        if pokemon:
                            config_dict_temp['scanners']['wildfilter'].append(pokemon.id)
                            wildfilter_names.append(pokemon.name)
                    if len(config_dict_temp['scanners']['wildfilter']) > 0:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description=_('Automatic wild filter will block: {wilds}').format(wilds=', '.join(wildfilter_names))))
                        break
                    else:
                        await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="Please enter at least one pokemon or **N** to turn off automatic wild filter."))
                        continue
        scanner_embed = discord.Embed(colour=discord.Colour.lighter_grey(), description='Do you want automatic **!research** reports using supported bots enabled?\n\nAny quest that a bot posts in a channel that Meowth also has access to will be converted to a **!research** report.\n\nRespond with: **N** to disable, or **Y** to enable:').set_author(name='Automatic Research Reports', icon_url=self.bot.user.avatar_url)
        scanner_embed.add_field(name=_('**Supported Bots:**'), value=_('NovaBot, PokeAlarm'))
        scanner_embed.add_field(name=_('**NovaBot / PokeAlarm Syntax:**'), value=_('Content must include: `!res <pokestop>|<lat>,<lng>|<task>|<reward>`'))
        await owner.send(embed=scanner_embed)
        await owner.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=str(config_dict_temp['scanners'].get('autoquest', False))).set_author(name=_("Current AutoQuest Setting"), icon_url=self.bot.user.avatar_url), delete_after=300)
        while True:
            wildconfigset = await self.bot.wait_for('message', check=(lambda message: (message.guild == None) and message.author == owner))
            if wildconfigset.content.lower() == 'y':
                config_dict_temp['scanners']['autoquest'] = True
                await owner.send(embed=discord.Embed(colour=discord.Colour.green(), description='Automatic Quest Reports enabled'))
                break
            elif wildconfigset.content.lower() == 'n':
                config_dict_temp['scanners']['autoquest'] = False
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='Automatic Quest Reports disabled'))
                break
            elif wildconfigset.content.lower() == 'cancel':
                await owner.send(embed=discord.Embed(colour=discord.Colour.red(), description='**CONFIG CANCELLED!**\n\nNo changes have been made.'))
                return None
            else:
                await owner.send(embed=discord.Embed(colour=discord.Colour.orange(), description="I'm sorry I don't understand. Please reply with either **N** to disable, or **Y** to enable."))
                continue
        ctx.config_dict_temp = config_dict_temp
        return ctx

def setup(bot):
    bot.add_cog(Configure(bot))

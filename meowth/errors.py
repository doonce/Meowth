
import discord
from discord.ext import commands
from discord.ext.commands.errors import CommandError
from inspect import signature, getfullargspec
import asyncio
import sys
import traceback
import time

class TeamSetCheckFail(CommandError):
    'Exception raised checks.teamset fails'
    pass

class WantSetCheckFail(CommandError):
    'Exception raised checks.wantset fails'
    pass

class WildSetCheckFail(CommandError):
    'Exception raised checks.wildset fails'
    pass

class ReportCheckFail(CommandError):
    'Exception raised checks.allowreport fails'
    pass

class RaidSetCheckFail(CommandError):
    'Exception raised checks.raidset fails'
    pass

class EXRaidSetCheckFail(CommandError):
    'Exception raised checks.exraidset fails'
    pass

class TrainSetCheckFail(CommandError):
    'Exception raised checks.trainset fails'
    pass

class ResearchSetCheckFail(CommandError):
    'Exception raised checks.researchset fails'
    pass

class InvasionSetCheckFail(CommandError):
    'Exception raised checks.invasionset fails'
    pass

class LureSetCheckFail(CommandError):
    'Exception raised checks.lureset fails'
    pass

class PVPSetCheckFail(CommandError):
    'Exception raised checks.pvpset fails'
    pass

class NestSetCheckFail(CommandError):
    'Exception raised checks.nestset fails'
    pass

class MeetupSetCheckFail(CommandError):
    'Exception raised checks.meetupset fails'
    pass

class ArchiveSetCheckFail(CommandError):
    'Exception raised checks.archiveset fails'
    pass

class InviteSetCheckFail(CommandError):
    'Exception raised checks.inviteset fails'
    pass

class CityChannelCheckFail(CommandError):
    'Exception raised checks.citychannel fails'
    pass

class WantChannelCheckFail(CommandError):
    'Exception raised checks.wantchannel fails'
    pass

class RaidChannelCheckFail(CommandError):
    'Exception raised checks.raidchannel fails'
    pass

class RSVPChannelCheckFail(CommandError):
    'Exception raised checks.rsvpchannel fails'
    pass

class EggChannelCheckFail(CommandError):
    'Exception raised checks.eggchannel fails'
    pass

class NonRaidChannelCheckFail(CommandError):
    'Exception raised checks.nonraidchannel fails'
    pass

class ActiveRaidChannelCheckFail(CommandError):
    'Exception raised checks.activeraidchannel fails'
    pass

class ActiveChannelCheckFail(CommandError):
    'Exception raised checks.activechannel fails'
    pass

class CityRaidChannelCheckFail(CommandError):
    'Exception raised checks.cityraidchannel fails'
    pass

class RegionEggChannelCheckFail(CommandError):
    'Exception raised checks.cityeggchannel fails'
    pass

class RegionExRaidChannelCheckFail(CommandError):
    'Exception raised checks.allowexraidreport fails'
    pass

class ExRaidChannelCheckFail(CommandError):
    'Exception raised checks.cityeggchannel fails'
    pass

class ResearchReportChannelCheckFail(CommandError):
    'Exception raised checks.researchreport fails'
    pass

class InvasionReportChannelCheckFail(CommandError):
    'Exception raised checks.invasionhreport fails'
    pass

class LureReportChannelCheckFail(CommandError):
    'Exception raised checks.lurereport fails'
    pass

class PVPReportChannelCheckFail(CommandError):
    'Exception raised checks.pvpreport fails'
    pass

class NestReportChannelCheckFail(CommandError):
    'Exception raised checks.nestreport fails'
    pass

class MeetupReportChannelCheckFail(CommandError):
    'Exception raised checks.meetupreport fails'
    pass

class TrainReportChannelCheckFail(CommandError):
    'Exception raised checks.trainreport fails'
    pass

class WildReportChannelCheckFail(CommandError):
    'Exception raised checks.wildreport fails'
    pass

class TradeChannelCheckFail(CommandError):
    'Exception raised checks.tradereport fails'
    pass

class NestChannelCheckFail(CommandError):
    'Exception raised checks.nestreport fails'
    pass

class TradeSetCheckFail(CommandError):
    'Exception raised checks.tradeset fails'
    pass

class GuildCheckFail(CommandError):
    'Exception raised checks.check_guild fails'
    pass

class EXInviteFail(CommandError):
    'Exception raised checks.check_invite fails'
    pass

async def delete_error(message, error):
    try:
        await message.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
        pass
    try:
        await error.delete()
    except (discord.errors.Forbidden, discord.errors.HTTPException, AttributeError):
        pass

def missing_arg_msg(ctx):
    prefix = ctx.prefix.replace(ctx.bot.user.mention, '@' + ctx.bot.user.name)
    command = ctx.invoked_subcommand or ctx.invoked_with
    callback = ctx.command.callback
    sig = list(signature(callback).parameters.keys())
    (args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations) = getfullargspec(callback)
    rq_args = []
    nr_args = []
    if defaults:
        rqargs = args[:(- len(defaults))]
    else:
        rqargs = args
    if varargs:
        if varargs != 'args':
            rqargs.append(varargs)
    arg_num = len(ctx.args) - 1
    try:
        sig.remove('ctx')
    except ValueError:
        pass
    try:
        sig.remove('self')
    except ValueError:
        pass
    args_missing = sig[arg_num:]
    msg = _("Meowth! I'm missing some details! Usage: {prefix}{command}").format(prefix=prefix, command=command)
    for a in sig:
        if kwonlydefaults:
            if a in kwonlydefaults.keys():
                msg += ' [{0}]'.format(a)
                continue
        if a in args_missing:
            msg += ' **<{0}>**'.format(a)
        else:
            msg += ' <{0}>'.format(a)
    return msg

def custom_error_handling(bot, logger):

    @bot.event
    async def on_error(event, *args, **kwargs):
        """Called when an event raises an uncaught exception"""
        timestr = time.strftime("%d/%m/%Y %H:%M", time.localtime())
        print(f"--------------------\nEXCEPTION: A {sys.exc_info()[0].__name__} exception has occured in {event}. Check outputlog for details.\n[{timestr}]: {sys.exc_info()[1]}\n--------------------")
        logger.exception(f'{traceback.format_exc()}')

    @bot.event
    async def on_command_error(ctx, error):
        channel = ctx.channel
        for report_dict in ctx.bot.channel_report_dicts:
            if channel and hasattr(channel, "guild") and channel.id in ctx.bot.guild_dict.get(channel.guild.id, {}).setdefault(report_dict, {}):
                break
        if ctx.prefix:
            prefix = ctx.prefix.replace(ctx.bot.user.mention, '@' + ctx.bot.user.name)
        else:
            prefix = ctx.bot._get_prefix(ctx.bot, ctx.message)
            prefix = prefix[-1]
        if isinstance(error, commands.MissingRequiredArgument):
            error = await ctx.channel.send(missing_arg_msg(ctx))
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, commands.BadArgument):
            error = await ctx.send_help(ctx.command)
            await asyncio.sleep(20)
            await delete_error(ctx.message, error)
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass
        elif isinstance(error, commands.CommandOnCooldown):
            if ctx.invoked_with == "starting":
                error = await channel.send(_("The command **{prefix}{cmd_name}** is on cooldown to prevent errors. If you still need to start, try again in {retry} seconds.").format(prefix=prefix, cmd_name=ctx.invoked_subcommand or ctx.invoked_with, retry=int(error.retry_after)))
            else:
                error = await channel.send(_("The command **{prefix}{cmd_name}** is on cooldown to prevent errors. Try again in {retry} seconds.").format(prefix=prefix, cmd_name=ctx.invoked_subcommand or ctx.invoked_with, retry=int(error.retry_after)))
            if error:
                await asyncio.sleep(10)
                await delete_error(ctx.message, error)
        elif isinstance(error, GuildCheckFail):
            msg = _('Meowth! Commands are not allowed in DM Channels. Please use **{prefix}{cmd_name}** in a server channel.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, TeamSetCheckFail):
            msg = _('Meowth! Team Management is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, WantSetCheckFail):
            msg = _('Meowth! Pokemon Notifications are not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, WildSetCheckFail):
            msg = _('Meowth! Wild Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ReportCheckFail):
            msg = _('Meowth! Reporting is not enabled for this channel. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, RaidSetCheckFail):
            msg = _('Meowth! Raid Management is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, EXRaidSetCheckFail):
            msg = _('Meowth! EX Raid Management is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, TrainSetCheckFail):
            msg = _('Meowth! Raid Trains are not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ResearchSetCheckFail):
            msg = _('Meowth! Research Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, InvasionSetCheckFail):
            msg = _('Meowth! Invasion Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, LureSetCheckFail):
            msg = _('Meowth! Lure Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, PVPSetCheckFail):
            msg = _('Meowth! PVP Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, MeetupSetCheckFail):
            msg = _('Meowth! Meetup Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ArchiveSetCheckFail):
            msg = _('Meowth! Channel Archiving is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, InviteSetCheckFail):
            msg = _('Meowth! EX Raid Invite is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, TradeSetCheckFail):
            msg = _('Meowth! Trading is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, NestSetCheckFail):
            msg = _('Meowth! Nest Reporting is not enabled on this server. **{prefix}{cmd_name}** is unable to be used.').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, CityChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, WantChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in the following channel').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            want_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('want', {}).get('report_channels', [])
            if len(want_channels) > 1:
                msg += _('s:\n')
            else:
                msg += _(': ')
            counter = 0
            for c in want_channels:
                channel = discord.utils.get(guild.channels, id=c)
                perms = ctx.author.permissions_in(channel)
                if not perms.read_messages:
                    continue
                if counter > 0:
                    msg += '\n'
                if channel:
                    msg += channel.mention
                else:
                    msg += '\n#deleted-channel'
                counter += 1
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, RaidChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in a Raid channel. Use **{prefix}list** in any ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('Region report channel to see active raids.')
            else:
                msg += _('of the following channels to see active raids:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, RSVPChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in a Raid channel. Use **{prefix}list** in any ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            raid_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            meetup_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('meetup', {}).get('report_channels', [])
            city_channels = {**raid_channels, **meetup_channels}
            if len(city_channels) > 10:
                msg += _('Region report channel to see active channels.')
            else:
                msg += _('of the following channels to see active channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, EggChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in an Egg channel. Use **{prefix}list** in any ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('Region report channel to see active raids.')
            else:
                msg += _('of the following channels to see active raids:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, NonRaidChannelCheckFail):
            msg = _("Meowth! **{prefix}{cmd_name}** can't be used in a Raid channel.").format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ActiveRaidChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in an Active Raid channel. Use **{prefix}list** in any ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            egg_check = bot.guild_dict[guild.id][report_dict].get(ctx.channel.id, {}).get('type', "")
            meetup = bot.guild_dict[guild.id][report_dict].get(ctx.channel.id, {}).get('meetup', {})
            if len(city_channels) > 10:
                msg += _('Region report channel to see active channels.')
            else:
                msg += _('of the following channels to see active channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            if egg_check == "egg" and not meetup:
                msg += _('\nThis is an egg channel. The channel needs to be activated with **{prefix}raid <pokemon>** before I accept commands!').format(prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ActiveChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in an Active channel. Use **{prefix}list** in any ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            egg_check = bot.guild_dict[guild.id][report_dict].get(ctx.channel.id, {}).get('type', "")
            meetup = bot.guild_dict[guild.id][report_dict].get(ctx.channel.id, {}).get('meetup', {})
            if len(city_channels) > 10:
                msg += _('Region report channel to see active raids.')
            else:
                msg += _('of the following channels to see active raids:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            if egg_check == "egg" and not meetup:
                msg += _('\nThis is an egg channel. The channel needs to be activated with **{prefix}raid <pokemon>** before I accept commands!').format(prefix=prefix)
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, CityRaidChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in either a Raid channel or ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, RegionEggChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in either a Raid Egg channel or ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('raid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, RegionExRaidChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in either a EX Raid channel or ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('exraid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, ExRaidChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in a EX Raid channel. Use **{prefix}list** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('exraid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel to see active raids.')
            else:
                msg += _('one of the following channels to see active raids:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, EXInviteFail):
            guild = ctx.guild
            msg = _('Meowth! {member}, you have not gained access to this raid! Use **{prefix}exinvite** in ').format(member=ctx.author.mention, cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('exraid', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel to gain access.')
            else:
                msg += _('one of the following channels to gain access:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(60)
            await delete_error(ctx.message, error)
        elif isinstance(error, ResearchReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('research', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, InvasionReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('invasion', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, LureReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('lure', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, PVPReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('pvp', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, MeetupReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('meetup', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, TrainReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('train', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, TradeChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('trade', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a trading channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, NestChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('nest', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a nest report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        elif isinstance(error, WildReportChannelCheckFail):
            guild = ctx.guild
            msg = _('Meowth! Please use **{prefix}{cmd_name}** in ').format(cmd_name=ctx.invoked_subcommand or ctx.invoked_with, prefix=prefix)
            city_channels = bot.guild_dict[guild.id].get('configure_dict', {}).get('wild', {}).get('report_channels', [])
            if len(city_channels) > 10:
                msg += _('a report channel.')
            else:
                msg += _('one of the following channels:')
                for c in city_channels:
                    channel = discord.utils.get(guild.channels, id=c)
                    perms = ctx.author.permissions_in(channel)
                    if not perms.read_messages:
                        continue
                    if channel:
                        msg += '\n' + channel.mention
                    else:
                        msg += '\n#deleted-channel'
            error = await ctx.channel.send(msg)
            await asyncio.sleep(10)
            await delete_error(ctx.message, error)
        else:
            timestr = time.strftime("%d/%m/%Y %H:%M", time.localtime())
            print(f"--------------------\nEXCEPTION: A {type(error).__name__} exception has occured in {ctx.command}. Check outputlog for details.\n[{timestr}]: {error}\n--------------------")
            logger.exception(type(error).__name__, exc_info=error)


import datetime
from discord.ext import commands
import discord.utils
from meowth import errors

def is_owner_check(ctx):
    author = ctx.author.id
    owner = ctx.bot.config['master']
    return author == owner

def is_owner():
    return commands.check(is_owner_check)

def is_manager_check(ctx):
    author = ctx.author.id
    manager_list = ctx.bot.config.get('managers', [])
    return author in manager_list or is_dev_check(ctx) or is_owner_check(ctx)

def is_manager():
    def predicate(ctx):
        if is_manager_check(ctx):
            return True
        else:
            return False
    return commands.check(predicate)

def is_dev_check(ctx):
    author = ctx.author.id
    dev_list = [288810647960158220]
    return author in dev_list

def is_dev():
    def predicate(ctx):
        if is_dev_check(ctx):
            return True
        else:
            return False
    return commands.check(predicate)

def check_permissions(ctx, perms):
    if not perms:
        return False
    ch = ctx.channel
    author = ctx.author
    resolved = ch.permissions_for(author)
    return all((getattr(resolved, name, None) == value for (name, value) in perms.items()))

def role_or_permissions(ctx, check, **perms):
    if check_permissions(ctx, perms):
        return True
    ch = ctx.channel
    author = ctx.author
    if ch.is_private:
        return False
    role = discord.utils.find(check, author.roles)
    return role is not None

def serverowner_or_permissions(**perms):
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        owner = ctx.guild.owner
        if ctx.author.id == owner.id:
            return True
        return check_permissions(ctx, perms)
    return commands.check(predicate)

def serverowner():
    return guildowner_or_permissions()

#configuration
def check_wantset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('want', {}).get('enabled', False)

def check_wantchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    want_channels = ctx.bot.guild_dict[guild.id]['configure_dict']['want'].get('report_channels', [])
    return channel.id in want_channels

def check_citychannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('report_channels', {}).keys()]
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('report_channels', [])])
    return channel.id in channel_list

def check_raidset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('enabled', False)

def check_raidreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_raidchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    raid_channels = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).keys()
    return channel.id in raid_channels

def check_eggchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    type = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('type', None)
    return type == 'egg'

def check_raidactive(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('active', False)

def check_exraidset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('enabled', False)

def check_exraidreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_inviteset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('invite', {}).get('enabled', False)

def check_exraidchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    level = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('egglevel', False)
    type =  ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('type', False)
    return (level == 'EX') or (type == 'exraid')

def check_meetupset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('meetup', {}).get('enabled', False)

def check_meetupreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('meetup', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_meetupchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    meetup =  ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('meetup', False)
    return meetup

def check_tradeset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('trade', {}).get('enabled', False)

def check_tradereport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('trade', {}).get('report_channels', [])]
    return channel.id in channel_list

def check_wildset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('enabled', False)

def check_wildreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_teamset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('team', {}).get('enabled', False)

def check_welcomeset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('welcome', {}).get('enabled', False)

def check_archiveset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('archive', {}).get('enabled', False)

def check_researchset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('enabled', False)

def check_researchreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_nestset(ctx):
    if ctx.guild is None:
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('enabled', False)

def check_nestreport(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('report_channels', [])]
    return channel.id in channel_list

def check_tutorialchannel(ctx):
    if ctx.guild is None:
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_dict = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('tutorial', {}).get('report_channels', {})]
    return channel.id in channel_dict

def dm_check(ctx, trainer):
    user = ctx.guild.get_member(trainer)
    if not user:
        return False
    perms = user.permissions_in(ctx.channel)
    if not perms.read_messages:
        return False
    mute = ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}).get(trainer, {}).get('alerts', {}).get('settings', {}).get('mute', False)
    report_time = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset']))
    start_time = ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}).get(trainer, {}).get('alerts', {}).get('settings', {}).get('active_start', False)
    end_time = ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}).get(trainer, {}).get('alerts', {}).get('settings', {}).get('active_end', False)
    if not start_time or not end_time:
        return True
    start_time = datetime.datetime.combine(report_time.date(), start_time)
    end_time = datetime.datetime.combine(report_time.date(), end_time)
    if start_time.time() > end_time.time() and report_time.time() > start_time.time():
        end_time = end_time + datetime.timedelta(days=1)
    elif start_time.time() > end_time.time() and report_time.time() < start_time.time():
        start_time = start_time + datetime.timedelta(days=-1)
    if (report_time > end_time or report_time < start_time) or mute:
        return False
    return True

#Decorators
def guildchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        return True
    return commands.check(predicate)

def allowreports():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidreport(ctx) or (check_eggchannel(ctx) and check_raidchannel(ctx)):
            return True
        elif check_exraidreport(ctx) or check_exraidchannel(ctx):
            return True
        elif check_wildreport(ctx):
            return True
        elif check_researchreport(ctx):
            return True
        elif check_tradereport(ctx):
            return True
        elif check_nestreport(ctx):
            return True
        else:
            raise errors.ReportCheckFail()
    return commands.check(predicate)

def allowraidreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidset(ctx):
            if check_raidreport(ctx) or check_tutorialchannel(ctx) or (check_eggchannel(ctx) and check_raidchannel(ctx)):
                return True
            else:
                raise errors.RegionEggChannelCheckFail()
        else:
            raise errors.RaidSetCheckFail()
    return commands.check(predicate)

def allowexraidreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_exraidset(ctx):
            if check_exraidreport(ctx) or check_exraidchannel(ctx):
                return True
            else:
                raise errors.RegionExRaidChannelCheckFail()
        else:
            raise errors.EXRaidSetCheckFail()
    return commands.check(predicate)

def allowwildreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_wildset(ctx):
            if check_wildreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.WildReportChannelCheckFail()
        else:
            raise errors.WildSetCheckFail()
    return commands.check(predicate)

def allowresearchreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_researchset(ctx):
            if check_researchreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.ResearchReportChannelCheckFail()
        else:
            raise errors.ResearchSetCheckFail()
    return commands.check(predicate)

def allownestreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_nestset(ctx):
            if check_nestreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.NestChannelCheckFail()
        else:
            raise errors.NestSetCheckFail()
    return commands.check(predicate)

def allowmeetupreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_meetupset(ctx):
            if check_meetupreport(ctx):
                return True
            else:
                raise errors.MeetupReportChannelCheckFail()
        else:
            raise errors.MeetupSetCheckFail()
    return commands.check(predicate)

def allowinvite():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_inviteset(ctx):
            if check_citychannel(ctx):
                return True
            else:
                raise errors.CityChannelCheckFail()
        else:
            raise errors.InviteSetCheckFail()
    return commands.check(predicate)

def allowteam():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_teamset(ctx):
            if not check_raidchannel(ctx):
                return True
            else:
                raise errors.NonRaidChannelCheckFail()
        else:
            raise errors.TeamSetCheckFail()
    return commands.check(predicate)

def allowwant():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_wantset(ctx):
            if check_wantchannel(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.WantChannelCheckFail()
        raise errors.WantSetCheckFail()
    return commands.check(predicate)

def allowtrade():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_tradeset(ctx):
            if check_tradereport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.TradeChannelCheckFail()
        else:
            raise errors.TradeSetCheckFail()
    return commands.check(predicate)

def allowarchive():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_archiveset(ctx):
            if check_raidchannel(ctx):
                return True
        raise errors.ArchiveSetCheckFail()
    return commands.check(predicate)

def citychannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_citychannel(ctx):
            return True
        raise errors.CityChannelCheckFail()
    return commands.check(predicate)

def raidchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidchannel(ctx):
            return True
        raise errors.RaidChannelCheckFail()
    return commands.check(predicate)

def exraidchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_exraidchannel(ctx):
            return True
        raise errors.ExRaidChannelCheckFail()
    return commands.check(predicate)

def nonraidchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if (not check_raidchannel(ctx)):
            return True
        raise errors.NonRaidChannelCheckFail()
    return commands.check(predicate)

def activeraidchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidchannel(ctx) and not check_meetupchannel(ctx):
            if check_raidactive(ctx):
                return True
        raise errors.ActiveRaidChannelCheckFail()
    return commands.check(predicate)

def activechannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidchannel(ctx):
            if check_raidactive(ctx):
                return True
        raise errors.ActiveChannelCheckFail()
    return commands.check(predicate)

def feature_enabled(names, ensure_all=False):
    def predicate(ctx):
        cfg = ctx.bot.guild_dict[ctx.guild.id]['configure_dict']
        enabled = [k for k, v in cfg.items() if v.get('enabled', False)]
        if isinstance(names, list):
            result = [n in enabled for n in names]
            return all(*result) if ensure_all else any(*result)
        if isinstance(names, str):
            return names in enabled
    return commands.check(predicate)

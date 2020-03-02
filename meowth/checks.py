
import datetime
from discord.ext import commands
import discord.utils
from meowth import errors

### User hierarchy

def is_dev_check(ctx):
    return ctx.author.id in [288810647960158220]

def is_dev():
    return commands.check(is_dev_check)

def is_owner_check(ctx):
    return ctx.author.id == ctx.bot.owner or is_dev_check(ctx)

def is_owner():
    return commands.check(is_owner_check)

def is_manager_check(ctx):
    return ctx.author.id in ctx.bot.managers or is_owner_check(ctx)

def is_manager():
    return commands.check(is_manager_check)

def is_guildowner_check(ctx):
    return ctx.author.id == ctx.guild.owner.id or is_manager_check(ctx)

def is_guildowner():
    return commands.check(is_guildowner_check)

def is_admin_check(ctx):
    if is_guildowner_check(ctx):
        return True
    if ctx.author.guild_permissions.manage_guild:
        return True
    return False

def is_admin():
    return commands.check(is_admin)

def is_mod_check(ctx):
    if is_admin_check(ctx):
        return True
    if ctx.author.permissions_in(ctx.channel).manage_messages:
        return True
    elif ctx.author.permissions_in(ctx.channel).manage_channel:
        return True
    elif ctx.author.permissions_in(ctx.channel).manage_roles:
        return True
    return False

def is_mod():
    return commands.check(is_mod_check)

###

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
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('want', {}).get('enabled', False)

def check_wantchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    want_channels = ctx.bot.guild_dict[guild.id]['configure_dict']['want'].get('report_channels', [])
    return channel.id in want_channels

def check_citychannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('report_channels', {}).keys()]
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('report_channels', [])])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('lure', {}).get('report_channels', {}).keys()])
    channel_list.extend([x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('pvp', {}).get('report_channels', {}).keys()])
    return channel.id in channel_list

def check_raidset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('enabled', False)

def check_raidreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('raid', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_rsvpchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    for report_dict in ctx.bot.channel_report_dicts:
        if channel.id in ctx.bot.guild_dict[guild.id].setdefault(report_dict, {}).keys():
            return True
    return False

def check_raidchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    raid_channels = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).keys()
    return channel.id in raid_channels

def check_exraidchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    raid_channels = ctx.bot.guild_dict[guild.id].setdefault('exraidchannel_dict', {}).keys()
    level = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('egg_level', False)
    type =  ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('type', False)
    return channel.id in raid_channels or level == 'EX' or type == 'exraid'

def check_hatchedraid(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    for report_dict in ctx.bot.channel_report_dicts:
        pokemon = ctx.bot.guild_dict[guild.id].setdefault(report_dict, {}).get(channel.id, {}).get('pkmn_obj', False)
        type = ctx.bot.guild_dict[guild.id].setdefault(report_dict, {}).get(channel.id, {}).get('type', False)
        if pokemon and type != "egg":
            return pokemon
    return False

def check_eggchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    type = ctx.bot.guild_dict[guild.id].setdefault('raidchannel_dict', {}).get(channel.id, {}).get('type', None)
    return type == "egg"

def check_exeggchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    type = ctx.bot.guild_dict[guild.id].setdefault('exraidchannel_dict', {}).get(channel.id, {}).get('type', None)
    return type == "egg"

def check_raidactive(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    for report_dict in ctx.bot.channel_report_dicts:
        active = ctx.bot.guild_dict[guild.id].setdefault(report_dict, {}).get(channel.id, {}).get('active', False)
        if active:
            return True
    return False

def check_exraidset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('enabled', False)

def check_exraidreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('exraid', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_inviteset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('invite', {}).get('enabled', False)

def check_meetupset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('meetup', {}).get('enabled', False)

def check_meetupreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('meetup', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_meetupchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    meetup_channels = ctx.bot.guild_dict[guild.id].setdefault('meetup_dict', {}).keys()
    return channel.id in meetup_channels

def check_trainset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('train', {}).get('enabled', False)

def check_trainreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('train', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_trainchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    train_channels = ctx.bot.guild_dict[guild.id].setdefault('raidtrain_dict', {}).keys()
    return channel.id in train_channels

def check_tradeset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('trade', {}).get('enabled', False)

def check_tradereport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('trade', {}).get('report_channels', [])]
    return channel.id in channel_list

def check_wildset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('enabled', False)

def check_wildreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('wild', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_teamset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('team', {}).get('enabled', False)

def check_welcomeset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('welcome', {}).get('enabled', False)

def check_archiveset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('archive', {}).get('enabled', False)

def check_invasionset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('invasion', {}).get('enabled', False)

def check_invasionreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('invasion', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_researchset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('enabled', False)

def check_researchreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('research', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_lureset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('lure', {}).get('enabled', False)

def check_pvpset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('pvp', {}).get('enabled', False)

def check_lurereport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('lure', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_pvpreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('pvp', {}).get('report_channels', {}).keys()]
    return channel.id in channel_list

def check_nestset(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    guild = ctx.guild
    return ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('enabled', False)

def check_nestreport(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_list = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('nest', {}).get('report_channels', [])]
    return channel.id in channel_list

def check_tutorialchannel(ctx):
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    channel = ctx.channel
    guild = ctx.guild
    channel_dict = [x for x in ctx.bot.guild_dict[guild.id]['configure_dict'].setdefault('tutorial', {}).get('report_channels', {})]
    return channel.id in channel_dict

def dm_check(ctx, trainer, report_type):
    user = ctx.guild.get_member(trainer)
    if ctx.guild is None or ctx.guild.id not in list(ctx.bot.guild_dict.keys()):
        return False
    if not user:
        return False
    if check_tutorialchannel(ctx) and user != ctx.author:
        return False
    perms = user.permissions_in(ctx.channel)
    if not perms.read_messages:
        return False
    mute = ctx.bot.guild_dict[ctx.guild.id].setdefault('trainers', {}).get(trainer, {}).get('alerts', {}).get('settings', {}).get('mute', {}).get(report_type, False)
    if mute:
        return False
    report_time = (ctx.message.created_at + datetime.timedelta(hours=ctx.bot.guild_dict[ctx.guild.id]['configure_dict']['settings']['offset']))
    time_setting = ctx.bot.guild_dict[ctx.guild.id].get('trainers', {}).get(trainer, {}).get('alerts', {}).get('settings', {}).get('active_hours', {}).get(report_time.strftime("%A").lower(), False)
    if not time_setting:
        return True
    start_time = time_setting.get('active_start', False)
    end_time = time_setting.get('active_end', False)
    start_time = datetime.datetime.combine(report_time.date(), start_time)
    end_time = datetime.datetime.combine(report_time.date(), end_time)
    if start_time.time() > end_time.time() and report_time.time() > start_time.time():
        end_time = end_time + datetime.timedelta(days=1)
    elif start_time.time() > end_time.time() and report_time.time() < start_time.time():
        start_time = start_time + datetime.timedelta(days=-1)
    if (report_time > end_time or report_time < start_time):
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
        if check_raidreport(ctx) or (check_eggchannel(ctx) or check_exeggchannel(ctx) and check_raidchannel(ctx)):
            return True
        elif check_exraidreport(ctx) or check_exraidchannel(ctx):
            return True
        elif check_wildreport(ctx):
            return True
        elif check_researchreport(ctx):
            return True
        elif check_lurereport(ctx):
            return True
        elif check_pvpreport(ctx):
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
            if check_raidreport(ctx) or check_tutorialchannel(ctx) or check_eggchannel(ctx) or check_exeggchannel(ctx):
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

def allowinvasionreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_invasionset(ctx):
            if check_invasionreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.InvasionReportChannelCheckFail()
        else:
            raise errors.InvasionSetCheckFail()
    return commands.check(predicate)

def allowlurereport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_lureset(ctx):
            if check_lurereport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.LureReportChannelCheckFail()
        else:
            raise errors.LureSetCheckFail()
    return commands.check(predicate)

def allowpvpreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_pvpset(ctx):
            if check_pvpreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.PVPReportChannelCheckFail()
        else:
            raise errors.PVPSetCheckFail()
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
            if check_meetupreport(ctx) or check_tutorialchannel(ctx):
                return True
            else:
                raise errors.MeetupReportChannelCheckFail()
        else:
            raise errors.MeetupSetCheckFail()
    return commands.check(predicate)

def meetupchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_meetupset(ctx):
            if check_meetupchannel(ctx):
                return True
            else:
                raise errors.MeetupReportChannelCheckFail()
        else:
            raise errors.MeetupSetCheckFail()
    return commands.check(predicate)

def allowtrainreport():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidset(ctx) and check_trainset(ctx):
            if check_raidreport(ctx) or check_tutorialchannel(ctx) or check_eggchannel(ctx) or check_raidchannel(ctx) or check_trainreport(ctx):
                return True
            else:
                raise errors.RegionEggChannelCheckFail()
        else:
            raise errors.TrainSetCheckFail()
    return commands.check(predicate)

def trainchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_trainset(ctx):
            if check_trainchannel(ctx):
                return True
            else:
                raise errors.TrainReportChannelCheckFail()
        else:
            raise errors.TrainSetCheckFail()
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
            if check_rsvpchannel(ctx):
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

def rsvpchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidchannel(ctx) or check_meetupchannel(ctx) or check_trainchannel(ctx) or check_exraidchannel(ctx):
            return True
        raise errors.RSVPChannelCheckFail()
    return commands.check(predicate)

def raidchannel():
    def predicate(ctx):
        if not ctx.guild:
            raise errors.GuildCheckFail()
        if check_raidchannel(ctx) or check_exraidchannel(ctx):
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
        if (check_exraidchannel(ctx) or check_raidchannel(ctx)) and not check_meetupchannel(ctx):
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
        cfg = ctx.bot.guild_dict.get(ctx.guild.id, {}).get('configure_dict', {})
        enabled = [k for k, v in cfg.items() if v.get('enabled', False)]
        if isinstance(names, list):
            result = [n in enabled for n in names]
            return all(*result) if ensure_all else any(*result)
        if isinstance(names, str):
            return names in enabled
    return commands.check(predicate)

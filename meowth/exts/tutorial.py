import asyncio
import copy
import logging

import discord
from discord.ext import commands


from meowth import utils
from meowth import checks
from meowth.exts import trade

logger = logging.getLogger("meowth")

class Tutorial(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.tutorial_cleanup())

    async def wait_for_cmd(self, tutorial_channel, newbie, command_name):

        # build check relevant to command
        def check(c):
            if not c.channel == tutorial_channel:
                return False
            if not c.author == newbie:
                return False
            if c.command.name == command_name:
                return True
            return False

        # wait for the command to complete
        cmd_ctx = await self.bot.wait_for(
            'command_completion', check=check, timeout=300)

        return cmd_ctx

    def get_overwrites(self, guild, member):
        return {
            guild.default_role: discord.PermissionOverwrite(
                read_messages=False),
            member: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True),
            guild.me: discord.PermissionOverwrite(
                read_messages=True)
            }

    async def tutorial_cleanup(self):
        await self.bot.wait_until_ready()
        logger.info('------ BEGIN ------')
        guilddict_temp = copy.deepcopy(self.bot.guild_dict)
        for guildid in guilddict_temp.keys():
            tutorial_dict = guilddict_temp[guildid]['configure_dict'].setdefault('tutorial', {}).setdefault('report_channels', {})
            for channelid in tutorial_dict:
                channel_exists = self.bot.get_channel(channelid)
                if not channel_exists:
                    try:
                        del guild_dict[guildid]['configure_dict']['tutorial']['report_channels'][channelid]
                    except KeyError:
                        pass
                    try:
                        del guild_dict[guildid]['configure_dict']['raid']['category_dict'][channelid]
                    except KeyError:
                        pass
                else:
                    newbie = False
                    ctx = False
                    for overwrite in channel_exists.overwrites:
                        if isinstance(overwrite[0], discord.Member):
                            if not overwrite[0].bot:
                                newbie = overwrite[0]
                    try:
                        tutorial_message = await channel_exists.get_message(tutorial_dict[channelid])
                    except (discord.errors.NotFound, discord.errors.Forbidden, discord.errors.HTTPException):
                        pass
                    if tutorial_message:
                        ctx = await self.bot.get_context(tutorial_message)
                    if ctx and newbie:
                        ctx.author = newbie
                        ctx.tutorial_channel = channel_exists
                        if not ctx.prefix:
                            prefix = self.bot._get_prefix(self.bot, ctx.message)
                            ctx.prefix = prefix[-1]
                        await ctx.tutorial_channel.send(f"Hey {newbie.mention} I think we were cut off due to a disconnection, let's try to start over.")
                        ctx.bot.loop.create_task(self._tutorial(ctx))

    async def want_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(),description=f"This server utilizes the **{ctx.prefix}want** command to help members receive push notifications about Pokemon they want! I keep your list saved and then send you a DM for wild spawns, nest spawns, and research reports. For raid bosses I will @mention you. Please make sure you have DMs enabled in order to receive alerts!\n\nTry the {ctx.prefix}want command!\nEx: `{ctx.prefix}want unown`").set_author(name="Want Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        try:
            await self.wait_for_cmd(ctx.tutorial_channel, ctx.author, 'want')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.green(),
                description=f"Great job!"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.red(),
                description=f"You took too long to complete the **{ctx.prefix}want** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)

            return False

        # clean up by removing tutorial from report channel config
        finally:
            del report_channels[ctx.tutorial_channel.id]

        return True

    async def wild_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(
            colour=discord.Colour.lighter_grey(),
            description=f"This server utilizes the **{ctx.prefix}wild** command to report wild spawns! When you use it, I will send a message summarizing the report and containing a link to my best guess of the spawn location. If users have **!want**ed your reported pokemon, I will DM them details! Your report must contain the name of the Pokemon followed by its location like **!wild <pokemon> <location>**.\n\nTry reporting a wild spawn!\n Ex: `{ctx.prefix}wild magikarp some park`").set_author(name="Wild Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        try:
            wild_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'wild')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(
                colour=discord.Colour.green(),
                description=f"Great job!"))

            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"The {ctx.bot.config['wild_omw']} emoji adds you to a list of trainers chasing the wild spawn and the {ctx.bot.config['wild_despawn']} emoji alerts others that it has despawned."))

            try:
                wild_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][wild_ctx.author.id]['wild_reports']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][wild_ctx.author.id]['wild_reports'] = wild_reports - 1
            except KeyError:
                pass

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report]['reportchannel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['wildreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}wild** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False

        # clean up by removing tutorial from report channel config
        finally:
            del report_channels[ctx.tutorial_channel.id]

        return True

    async def raid_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
        if config['raid']['categories'] == "region":
            category_dict = config['raid']['category_dict']
            category_dict[tutorial_channel.id] = tutorial_channel.category_id
        tutorial_channel = ctx.tutorial_channel
        prefix = ctx.prefix
        raid_channel = None
        tier5 = str(ctx.bot.raid_info['raid_eggs']["5"]['pokemon'][0]).lower()

        async def timeout_raid(cmd):
            if raid_channel:
                await raid_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}{cmd}** command! This channel will be deleted in ten seconds."))
            await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}{cmd}** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            del report_channels[tutorial_channel.id]
            if config['raid']['categories'] == "region":
                del category_dict[tutorial_channel.id]
            if raid_channel:
                await raid_channel.delete()
            return

        msg = await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{prefix}raid** command to report raids! When you use it, I will send a message summarizing the report and create a text channel for coordination. \nThe report must contain, in this order: The Pokemon (if an active raid) or raid level (if an egg), and the location;\nthe report may optionally contain the weather (see **{prefix}help weather** for accepted options) and the minutes remaining until hatch or expiry (at the end of the report) \n\nTry reporting a raid!\nEx: `{prefix}raid {tier5} local church cloudy 42`").set_author(name="Raid Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        try:
            while True:
                raid_ctx = await self.wait_for_cmd(
                    tutorial_channel, ctx.author, 'raid')

                # get the generated raid channel
                raid_channel = raid_ctx.raid_channel

                if raid_channel:
                    break

                # acknowledge failure and redo wait_for
                await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.orange(), description=f"Doesn't look like it worked. Make sure you're not missing any arguments from your raid command and try again."))

            # acknowledge and redirect to new raid channel
            await tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job! Let's head into the new raid channel you just created: {raid_channel.mention}"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('raid')
            return False

        # post raid help info prefix, avatar, user
        helpembed = await utils.get_raid_help(
            ctx.prefix, ctx.bot.user.avatar_url)

        await raid_channel.send(
            f"This is an example of a raid channel. Here is a list of "
            "commands that can be used in here:", embed=helpembed)

        try:
            if raid_ctx.message.content.split()[1].isdigit():
                egg_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['egg_reports']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['egg_reports'] = egg_reports - 1
            else:
                raid_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['raid_reports']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][raid_ctx.author.id]['raid_reports'] = raid_reports - 1
        except KeyError:
            pass


        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Try expressing interest in this raid!\n\nEx: `{prefix}interested 5 m3 i1 v1` would mean 5 trainers: 3 Mystic, 1 Instinct, 1 Valor"))

        # wait for interested status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'interested')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('interested')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job! To save time, you can also use **{prefix}i** as an alias for **{prefix}interested**."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try letting people know that you are on your way!\n\nEx: `{prefix}coming`"))

        # wait for coming status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'coming')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('coming')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! Note that if you have already specified your party in a previous command, you do not have to again for the current raid unless you are changing it. Also, **{prefix}c** is an alias for **{prefix}coming**."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try letting people know that you have arrived at the raid!\n\nEx: `{prefix}here`"))

        # wait for here status update
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'here')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('here')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Good! Please note that **{prefix}h** is an alias for **{prefix}here**"))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Now try checking to see everyone's RSVP status for this raid!\n\nEx: `{prefix}list`"))

        # wait for list command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'list')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('list')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Awesome! Since no one else is on their way, try using the **{prefix}starting** command to move everyone on the 'here' list to a lobby!"))

        # wait for starting command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'starting')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('starting')
            return False

        # acknowledge and continue with pauses between
        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! You are now listed as being 'in the lobby', where you will remain for two minutes until the raid begins. In that time, anyone can request a backout with the **{prefix}backout** command. If the person requesting is in the lobby, the backout is automatic. If it is someone who arrived at the raid afterward, confirmation will be requested from a lobby member. When a backout is confirmed, all members will be returned to the 'here' list."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"A couple of notes about raid channels. Meowth has partnered with Pokebattler to give you the best counters for each raid boss in every situation. You can set the weather in the initial raid report, or with the **{prefix}weather** command. You can select the moveset using the reactions in the initial counters message. If you have a Pokebattler account, you can use **{prefix}set pokebattler <id>** to link them! After that, the **{prefix}counters**  command will DM you your own counters pulled from your Pokebox."))

        await asyncio.sleep(1)
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"Last thing: if you need to update the expiry time, use **{prefix}timerset <minutes left>**\n\nFeel free to play around with the commands here for a while. When you're finished, type `{prefix}timerset 0` and the raid will expire."))

        # wait for timerset command completion
        try:
            await self.wait_for_cmd(
                raid_channel, ctx.author, 'timerset')

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await timeout_raid('timerset')
            return False

        # acknowledge and direct member back to tutorial channel
        await raid_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great! Now return to {tutorial_channel.mention} to continue the tutorial. This channel will be deleted in ten seconds."))

        await tutorial_channel.send(f"Hey {ctx.author.mention}, once I'm done cleaning up the raid channel, the tutorial will continue here!")

        await asyncio.sleep(10)

        # remove tutorial raid channel
        await raid_channel.delete()
        raid_channel = None
        del report_channels[tutorial_channel.id]
        if config['raid']['categories'] == "region":
            del category_dict[tutorial_channel.id]

        return True

    async def research_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}research** command to report field research tasks! There are two ways to use this command: **{ctx.prefix}research** will start an interactive session where I will prompt you for the task, location, and reward of the research task. You can also use **{ctx.prefix}research <pokestop>, <task>, <reward>** to submit the report all at once.\n\nTry it out by typing `{ctx.prefix}research` and then a random pokestop, task, and reward.").set_author(name="Research Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        # wait for research command completion
        try:
            research_ctx = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'research')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            try:
                research_reports = ctx.bot.guild_dict[ctx.guild.id]['trainers'][research_ctx.author.id]['research_reports']
                ctx.bot.guild_dict[ctx.guild.id]['trainers'][research_ctx.author.id]['research_reports'] = research_reports - 1
            except KeyError:
                pass

            await asyncio.sleep(1)

            for report in ctx.bot.guild_dict[ctx.guild.id]['questreport_dict']:
                if ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report]['reportchannel'] == ctx.tutorial_channel.id:
                    await utils.expire_dm_reports(ctx.bot, ctx.bot.guild_dict[ctx.guild.id]['questreport_dict'][report].get('dm_dict', {}))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}research** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False

        # clean up by removing tutorial from report channel config
        finally:
            del report_channels[ctx.tutorial_channel.id]

        return True

    async def team_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}team** command to allow members to select which Pokemon Go team they belong to! Type `{ctx.prefix}team mystic` for example if you are in Team Mystic.").set_author(name="Team Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id
        # wait for team command completion
        try:
            await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'team')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}team** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False

        return True

    async def trade_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
        trade_msg = False

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}trade** command to list your pokemon up for trade. You can list one at a time using command: **{ctx.prefix}trade <pokemon>**. You can also use forms of pokemon such as `alolan vulpix`, `unown y`, or `shiny absol`.\nEx: `{ctx.prefix}trade unown y`").set_author(name="Trade Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        # wait for trade command completion
        try:
            trade_msg = await self.wait_for_cmd(
                ctx.tutorial_channel, ctx.author, 'trade')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))

            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"The number emojis make an offer for that pokemon and the \u23f9 emoji cancels the listing. Other interaction will take place in DM."))

            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}research** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)
            return False

        # clean up by removing tutorial from report channel config
        finally:
            del report_channels[ctx.tutorial_channel.id]
            if trade_msg:
                del ctx.bot.guild_dict[ctx.guild.id]['trade_dict'][trade_msg.channel.id]

        return True

    async def nest_tutorial(self, ctx, config):
        report_channels = config.setdefault('tutorial', {}).setdefault('report_channels', {})
        ctx.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.tutorial_channel.id] = {'list': ['hershey park'], 'hershey park': {'location':'40.28784,-76.65547', 'reports':{}}}

        msg = await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{ctx.prefix}nest** command to keep track of nesting pokemon. You can report one using command: **{ctx.prefix}nest <pokemon>**.\nEx: `{ctx.prefix}nest magikarp`").set_author(name="Nest Tutorial", icon_url=ctx.bot.user.avatar_url))

        report_channels[ctx.tutorial_channel.id] = msg.id

        try:
            await self.wait_for_cmd(ctx.tutorial_channel, ctx.author, 'nest')

            # acknowledge and wait a second before continuing
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.green(), description=f"Great job!"))
            await asyncio.sleep(1)

        # if no response for 5 minutes, close tutorial
        except asyncio.TimeoutError:
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.red(), description=f"You took too long to complete the **{ctx.prefix}nest** command! This channel will be deleted in ten seconds."))
            await asyncio.sleep(10)

            return False

        # clean up by removing tutorial from report channel config
        finally:
            del report_channels[ctx.tutorial_channel.id]
            del ctx.bot.guild_dict[ctx.guild.id]['nest_dict'][ctx.tutorial_channel.id]

        return True

    @commands.group(invoke_without_command=True)
    @checks.guildchannel()
    async def tutorial(self, ctx):
        """Launches an interactive tutorial session for Meowth.

        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""

        newbie = ctx.author
        guild = ctx.guild
        prefix = ctx.prefix

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)
        await self._tutorial(ctx)

    async def _tutorial(self, ctx):
        # get tutorial settings
        cfg = self.bot.guild_dict[ctx.guild.id]['configure_dict']
        enabled = [k for k, v in cfg.items() if v.get('enabled', False)]

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the server commands! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:

            # start want tutorial
            if 'want' in enabled:
                completed = await self.want_tutorial(ctx, cfg)
                if not completed:
                    return

            # start wild tutorial
            if 'wild' in enabled:
                completed = await self.wild_tutorial(ctx, cfg)
                if not completed:
                    return

            # start raid
            if 'raid' in enabled:
                completed = await self.raid_tutorial(ctx, cfg)
                if not completed:
                    return

            # start exraid
            if 'exraid' in enabled:
                invitestr = ""

                if 'invite' in enabled:
                    invitestr = (
                        "The text channels that are created with this command "
                        f"are read-only until members use the **{prefix}invite** "
                        "command.")

                await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This server utilizes the **{prefix}exraid** command to report EX raids! When you use it, I will send a message summarizing the report and create a text channel for coordination. {invitestr}\nThe report must contain only the location of the EX raid.\n\nDue to the longer-term nature of EX raid channels, we won't try this command out right now.").set_author(name="EX Raid Tutorial", icon_url=self.bot.user.avatar_url))

            # start research
            if 'research' in enabled:
                completed = await self.research_tutorial(ctx, cfg)
                if not completed:
                    return

            # start nest
            if 'nest' in enabled:
                completed = await self.nest_tutorial(ctx, cfg)
                if not completed:
                    return

            # start trade
            if 'trade' in enabled:
                completed = await self.trade_tutorial(ctx, cfg)
                if not completed:
                    return

            # start team
            if 'team' in enabled:
                completed = await self.team_tutorial(ctx, cfg)
                if not completed:
                    return

            # finish tutorial
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(30)

        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('want')
    async def want(self, ctx):
        """Launches an tutorial session for the want feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the want command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.want_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('wild')
    async def wild(self, ctx):
        """Launches an tutorial session for the wild feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through wild command."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the wild command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.wild_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('raid')
    async def raid(self, ctx):
        """Launches an tutorial session for the raid feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the raid commands."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the raid command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.raid_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('research')
    async def research(self, ctx):
        """Launches an tutorial session for the research feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the research command."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the research command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.research_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('trade')
    async def trade(self, ctx):
        """Launches an tutorial session for the research feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the research command."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the trade command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.trade_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('team')
    async def team(self, ctx):
        """Launches an tutorial session for the team feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the team command."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the team command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.team_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

    @tutorial.command()
    @checks.feature_enabled('nest')
    async def nest(self, ctx):
        """Launches an tutorial session for the nest feature.

        Meowth will create a private channel and initiate a
        conversation that walks you through the various commands
        that are enabled on the current server."""

        newbie = ctx.author
        guild = ctx.guild

        # get channel overwrites
        ows = self.get_overwrites(guild, newbie)

        # create tutorial channel
        name = utils.sanitize_channel_name(newbie.display_name+"-tutorial")
        ctx.tutorial_channel = await guild.create_text_channel(
            name, overwrites=ows)
        await utils.safe_delete(ctx.message)
        await ctx.send(
            ("Meowth! I've created a private tutorial channel for "
             f"you! Continue in {ctx.tutorial_channel.mention}"),
            delete_after=20.0)

        # get tutorial settings
        cfg = self.bot.guild_dict[guild.id]['configure_dict']

        await ctx.tutorial_channel.send(
            f"Hi {ctx.author.mention}! I'm Meowth, a Discord helper bot for "
            "Pokemon Go communities! I created this channel to teach you "
            "about the nest command! You can abandon this tutorial at any time "
            "and I'll delete this channel after five minutes. "
            "Let's get started!\n\n"
            "Just so you know, across all of Meowth, **<> denote required arguments"
            ", [] denote optional arguments** and you don't type the <>s or []s.")

        try:
            await self.nest_tutorial(ctx, cfg)
            await ctx.tutorial_channel.send(embed=discord.Embed(colour=discord.Colour.lighter_grey(), description=f"This concludes the Meowth tutorial! This channel will be deleted in 30 seconds."))

            await asyncio.sleep(10)
        finally:
            await ctx.tutorial_channel.delete()

def setup(bot):
    bot.add_cog(Tutorial(bot))

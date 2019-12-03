# bot token from discord developers
bot_token = 'token_here'

# default bot settings
default_prefix = '!'
master = 123123123123123123
bot_coowners = []
managers = [123123123123123123, 123123123123123123, 123123123123123123]

# default language
bot_language = 'en'
pokemon_language = 'en'

# team settings
team_dict = {"mystic":":mystic:", "valor":":valor:", "instinct":":instinct:", "harmony":":harmony:"}
unknown = ":grey_question:"

# raid settings
allow_assume = {"EX":"True", "5":"True", "4":"False", "3":"False", "2":"False", "1":"False"}

# status emoji
omw_id = ":omw:"
here_id = ":here:"

# type emoji; These can be custom or discord alias
# Example:  Custom: `<:emojiname:emojiid>` | Alias: `:emojiname`
type_id_dict = {
    "normal"   : "<:normal:123123123123123123>",
    "fire"     : "<:fire1:123123123123123123>",
    "water"    : "<:water:123123123123123123>",
    "electric" : "<:electric:123123123123123123>",
    "grass"    : "<:grass:123123123123123123>",
    "ice"      : "<:ice:123123123123123123>",
    "fighting" : "<:fighting:123123123123123123>",
    "poison"   : "<:poison:123123123123123123>",
    "ground"   : "<:ground:123123123123123123>",
    "flying"   : "<:flying:123123123123123123>",
    "psychic"  : "<:psychic:123123123123123123>",
    "bug"      : "<:bug1:123123123123123123>",
    "rock"     : "<:rock:123123123123123123>",
    "ghost"    : "<:ghost1:123123123123123123>",
    "dragon"   : "<:dragon1:123123123123123123>",
    "dark"     : "<:dark:123123123123123123>",
    "steel"    : "<:steel:123123123123123123>",
    "fairy"    : "<:fairy:123123123123123123>"
}

# custom_emoji for reactions and general use; These must be unicode or custom emoji. Not discord alias
# Example: Custom:`<:emojiname:emojiid>` | Standard: Use https://gist.github.com/Vexs/629488c4bb4126ad2a9909309ed6bd7
# If "surrogates" error use https://www.fileformat.info/index.htm python source code
custom_emoji = {
    'bullet': "\U0001F539",
    'research_complete' : "\u2705",
    'research_expired' : "\U0001F4A8",
    'res_candy' : "\U0001F36C",
    'res_dust' : "\U00002b50",
    'res_encounter' : "\U00002753",
    'res_revive' : "\U00002764\U0000fe0f",
    'res_ball' : "\u26be",
    'res_potion' : "\U0001F48A",
    'res_berry' : "\U0001F353",
    'res_other' : "\U0001F539",
    'raid_maybe' : "\U00002753",
    'raid_omw' : "\U0001F3CE",
    'raid_here' : "\U0001F4CD",
    'raid_cancel' : "\u274C",
    'raid_info' : "\u2139",
    'wild_omw' : "\U0001F3CE",
    'wild_despawn' : "\U0001F4A8",
    'wild_catch' : "\u2705",
    'wild_info' : "\u2139",
    'wild_bullet' : "\U0001F539",
    'trade_stop' : "\u23f9",
    'trade_accept' : "\u2705",
    'trade_reject' : "\u274e",
    'trade_complete' : "\u2611",
    'trade_bullet' : "\U0001F539",
    'answer_yes' : "\u2705",
    'answer_no' : "\u274e",
    'answer_cancel' : "\u274c",
    'command_done' : "\u2611",
    'huntr_report' : "\u2705",
    'shiny_chance' : "\u2728",
    'windy':"\U0001F343",
    'snowy':"\U00002744\U0000fe0f",
    'partlycloudy':"\U0001f325\U0000fe0f",
    'rainy':"\U0001f327\U0000fe0f",
    'foggy':"\U0001f32b\U0000fe0f",
    'cloudy':"\U00002601\U0000fe0f",
    'clear':"\U00002600\U0000fe0f",
    'invasion_complete':"\U0001f1f7",
    'invasion_expired':"\U0001F4A8"
}

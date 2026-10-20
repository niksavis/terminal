local wezterm = require("wezterm")
local original_on = wezterm.on
local registered = {}

wezterm.on = function(event, callback)
  assert(event ~= "format-tab-title", "custom format-tab-title callback is forbidden")
  registered[event] = true
  return original_on(event, callback)
end

local script_dir = assert(wezterm.config_file:match("^(.*)[/\\]"))
local ok, config = pcall(dofile, script_dir .. "/../terminal_setup/templates/wezterm.lua")
wezterm.on = original_on
if not ok then
  wezterm.log_error(config)
  error(config)
end
assert(config.enable_tab_bar == true, "tabs must remain enabled")
assert(config.use_fancy_tab_bar == true, "fancy tabs must remain enabled")
assert(registered["update-right-status"], "status footer callback must remain enabled")

local is_windows = wezterm.target_triple:find("windows") ~= nil
local is_wsl = os.getenv("WSL_DISTRO_NAME") ~= nil or os.getenv("WSL_INTEROP") ~= nil
if is_windows or is_wsl then
  assert(config.front_end == "Software", "Windows and WSL must retain Software rendering")
end

assert(config.max_fps == 30, "max_fps must remain 30")
assert(config.animation_fps == 10, "animation_fps must remain 10")
assert(config.cursor_blink_rate == 0, "cursor blinking must remain disabled")
assert(config.scrollback_lines == 10000, "scrollback must remain 10000 lines")
assert(config.status_update_interval == 3000, "status interval must remain 3000 ms")
wezterm.log_info("TERMINAL_CALLBACK_CHECK_PASS")
return config

local wezterm = require("wezterm")
local register = wezterm.on

wezterm.on = function(name, callback)
  assert(name ~= "format-tab-title", "Custom tab formatting converts the full config on every title update")
  return register(name, callback)
end

local config = dofile(wezterm.config_dir .. "/../terminal_setup/templates/wezterm.lua")
assert(config.enable_tab_bar, "The tab bar must remain available")
if wezterm.target_triple:find("windows") or os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP") then
  assert(config.front_end == "Software", "Preserve the existing GPU workaround")
end
wezterm.log_warn("TERMINAL_CALLBACK_CHECK_PASS")
return config

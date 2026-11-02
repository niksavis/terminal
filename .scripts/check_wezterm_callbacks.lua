local wezterm = require("wezterm")
local script_dir = assert(wezterm.config_file:match("^(.*)[/\\]"))
local template = script_dir .. "/../terminal_setup/templates/wezterm.lua"
local original_on = wezterm.on
local original_triple = wezterm.target_triple
local original_getenv = os.getenv
local original_wsl_domains = wezterm.default_wsl_domains
local footer_calls = 0
local platforms_checked = 0
local blocked_apis = {
  { wezterm, "run_child_process" },
  { wezterm, "background_child_process" },
  { io, "open" },
  { io, "popen" },
  { os, "execute" },
}

local function exercise_footer(callback)
  local last_status
  local window = {
    active_workspace = function() return "check-workspace" end,
    set_right_status = function(_, text) last_status = text end,
  }
  for _, cwd in ipairs({
    "/work/check-project",
    "C:\\work\\check-project",
    "//wsl.localhost/Ubuntu-24.04/work/check-project/",
    false,
  }) do
    local pane = {
      get_current_working_dir = function() return cwd and { file_path = cwd } or nil end,
    }
    for _ = 1, 100 do
      callback(window, pane)
      footer_calls = footer_calls + 1
      assert(last_status:find("check-workspace", 1, true), "footer must retain workspace")
      local expected = cwd and "check-project" or "~"
      assert(last_status:find(expected, 1, true), "footer must retain cwd or its fallback")
    end
  end
end

local function key_action(config, key, mods)
  for _, binding in ipairs(config.keys) do
    if binding.key == key and binding.mods == mods then
      return binding.action
    end
  end
  error("missing key binding " .. mods .. "+" .. key)
end

local function exercise_new_tab_button(config, callbacks)
  local new_tab_action = key_action(config, "t", "CTRL|SHIFT")
  assert(key_action(config, "c", "LEADER") == new_tab_action, "LEADER c must open the same tab as CTRL+SHIFT+T")
  assert(#callbacks == 1, "new tab button must have exactly one handler")
  local pane = { get_current_working_dir = function() return { file_path = "//wsl.localhost/Ubuntu-24.04/work/" } end }
  local performed = {}
  local window = { perform_action = function(_, action, target) table.insert(performed, { action, target }) end }
  assert(callbacks[1](window, pane, "Left", "default") == false, "left click must replace the default action")
  assert(#performed == 1 and performed[1][1] == new_tab_action and performed[1][2] == pane, "left click must open the WSL home tab")
  for _, button in ipairs({ "Right", "Middle" }) do
    assert(callbacks[1](window, pane, button, "default") == nil, button .. " click must keep the default action")
  end
  assert(#performed == 1, "only a left click may open the WSL home tab")
end

local function check_platform(case)
  wezterm.target_triple = case.triple
  wezterm.default_wsl_domains = function()
    return { { name = "WSL:Ubuntu-24.04", distribution = "Ubuntu-24.04" } }
  end
  os.getenv = function(name)
    if name == "WSL_DISTRO_NAME" or name == "WSL_INTEROP" then
      return case.wsl and "fixture" or nil
    end
    return original_getenv(name)
  end
  local registered = {}
  wezterm.on = function(event, callback)
    assert(event ~= "format-tab-title", "custom format-tab-title callback is forbidden")
    assert(event ~= "format-window-title", "custom format-window-title callback is forbidden")
    registered[event] = registered[event] or {}
    table.insert(registered[event], callback)
  end
  local config = dofile(template)
  assert(config.enable_tab_bar == true, "tabs must remain enabled")
  assert(config.use_fancy_tab_bar == true, "fancy tabs must remain enabled")
  assert(config.enable_kitty_graphics == false, "Kitty graphics must be disabled by default")
  if case.software then
    assert(config.front_end == "Software", "Windows and WSL must retain Software rendering")
  else
    assert(config.front_end == nil, "native builds must inherit the upstream renderer default")
  end
  assert(config.max_fps == 30, "max_fps must remain 30")
  assert(config.animation_fps == 10, "animation_fps must remain 10")
  assert(config.cursor_blink_rate == 0, "cursor blinking must remain disabled")
  assert(config.scrollback_lines == 10000, "scrollback must remain 10000 lines")
  assert(config.status_update_interval == 3000, "status interval must remain 3000 ms")
  assert(registered["update-right-status"], "status footer callback must remain enabled")
  if case.windows then
    assert(config.default_domain == "WSL:Ubuntu-24.04", "Windows must default to the WSL domain")
    exercise_new_tab_button(config, registered["new-tab-button-click"] or {})
  else
    assert(registered["new-tab-button-click"] == nil, "native builds must keep the default new tab button")
  end

  for _, api in ipairs(blocked_apis) do
    api.original = api[1][api[2]]
    api[1][api[2]] = function() error("blocking callback operation: " .. api[2]) end
  end
  for _, callback in ipairs(registered["update-right-status"]) do
    exercise_footer(callback)
  end
  for _, api in ipairs(blocked_apis) do
    api[1][api[2]] = api.original
  end
end

local ok, err = pcall(function()
  for _, case in ipairs({
    { triple = "x86_64-pc-windows-msvc", windows = true, software = true },
    { triple = "x86_64-unknown-linux-gnu", wsl = true, software = true },
    { triple = "x86_64-unknown-linux-gnu" },
    { triple = "aarch64-apple-darwin" },
  }) do
    check_platform(case)
    platforms_checked = platforms_checked + 1
  end
end)
wezterm.on = original_on
wezterm.target_triple = original_triple
os.getenv = original_getenv
wezterm.default_wsl_domains = original_wsl_domains
for _, api in ipairs(blocked_apis) do
  if api.original then
    api[1][api[2]] = api.original
  end
end
if not ok then
  wezterm.log_error(err)
  error(err)
end
local config = dofile(template)
wezterm.log_info(string.format("TERMINAL_CALLBACK_CHECK_PASS: %d platform inputs; %d footer calls", platforms_checked, footer_calls))
return config

return function(config)
  config.color_scheme = "Tokyo Night"
  config.foreground_text_hsb = { hue = 1.0, saturation = 1.0, brightness = 1.0 }
  config.window_background_opacity = 1.0
  config.text_background_opacity = 0.20
  config.colors = {
    foreground = "#C8D3F5",
    background = "#101B2A",
    cursor_bg = "#82AAFF",
    cursor_border = "#82AAFF",
    cursor_fg = "#101B2A",
    selection_bg = "#29436B",
    selection_fg = "#E6EBFF",
    split = "#334769",
    ansi = { "#1B2940", "#FF757F", "#C3E88D", "#FFC777", "#82AAFF", "#C099FF", "#86E1FC", "#C8D3F5" },
    brights = { "#4D5B7D", "#FF98A4", "#D3F3A5", "#FFDA96", "#A6C4FF", "#D4B5FF", "#B0EEFF", "#E6EBFF" },
    tab_bar = {
      background = "#0A111E",
      active_tab = { bg_color = "#223858", fg_color = "#E6EBFF", intensity = "Bold" },
      inactive_tab = { bg_color = "#111F33", fg_color = "#A6B4D8" },
      inactive_tab_hover = { bg_color = "#29436B", fg_color = "#E6EBFF" },
      new_tab = { bg_color = "#111F33", fg_color = "#A6B4D8" },
      new_tab_hover = { bg_color = "#29436B", fg_color = "#E6EBFF" },
    },
  }
  config.window_frame = config.window_frame or {}
  config.window_frame.active_titlebar_bg = "#0A111E"
  config.window_frame.inactive_titlebar_bg = "#0A111E"
  config.window_frame.active_titlebar_fg = "#C8D3F5"
  config.window_frame.inactive_titlebar_fg = "#A6B4D8"
end

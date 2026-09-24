#!/usr/bin/env bash

if [ -n "${LC_ALL:-}" ]; then
  export LC_CTYPE="$LC_ALL"
  export LC_ALL=""
fi
export LC_NUMERIC=C
probe=$'█'
if [ "${#probe}" != 1 ]; then
  export LC_CTYPE=C.UTF-8
fi

shopt -s extglob
input=$(cat)

case "$OSTYPE" in
  msys* | cygwin*) NERDFONT=${STATUSLINE_NERDFONT:-0} ;;
  *) NERDFONT=${STATUSLINE_NERDFONT:-1} ;;
esac

F=()
while IFS= read -r line || [ -n "$line" ]; do F+=("$line"); done < <(
  printf '%s' "$input" | jq -r '
    (.model.display_name // "?"),
    (.effort.level // ""),
    (.workspace.project_dir // .cwd // ""),
    (.workspace.git_worktree // ""),
    (.cwd // .workspace.current_dir // ""),
    (.cost.total_cost_usd // 0),
    (.cost.total_duration_ms // 0),
    (.cost.total_lines_added // 0),
    (.cost.total_lines_removed // 0),
    (.context_window.used_percentage // 0),
    (.context_window.total_input_tokens // 0),
    (.context_window.context_window_size // 0),
    (.rate_limits.five_hour.used_percentage // ""),
    (.rate_limits.five_hour.resets_at // ""),
    (.rate_limits.seven_day.used_percentage // ""),
    (.rate_limits.seven_day.resets_at // "")' 2>/dev/null | tr -d '\r'
)
model=${F[0]}; effort=${F[1]}; proj=${F[2]}; wt=${F[3]}; cwd=${F[4]}
cost=${F[5]}; dur=${F[6]}; added=${F[7]}; removed=${F[8]}
ctxpct=${F[9]}; ctxtok=${F[10]}; ctxmax=${F[11]}
h5=${F[12]}; h5r=${F[13]}; wk=${F[14]}; wkr=${F[15]}
[ -z "$model" ] && exit 0

ccfile="${CLAUDE_CONFIG_DIR:-$HOME}/.claude.json"
M=()
while IFS= read -r line || [ -n "$line" ]; do M+=("$line"); done < <(
  jq -r '
    .cachedUsageUtilization as $u
    | [ ($u.utilization.limits // [])[]
        | select(.scope.model.display_name != null and .percent != null) ]
    | sort_by(-.percent)[0] // empty
    | (.scope.model.display_name),
      (.percent | floor | tostring),
      (($u.fetchedAtMs // 0) / 1000 | floor | tostring)' "$ccfile" 2>/dev/null | tr -d '\r'
)
mdl=${M[0]:-}; mdlpct=${M[1]:-}; mdlat=${M[2]:-0}

cols=${STATUSLINE_WIDTH:-${COLUMNS:-}}
[ -z "$cols" ] && cols=$(tput cols 2>/dev/null || echo 120)

E=$'\033['; R="${E}0m"; BOLD="${E}1m"
FT="${E}38;2;192;202;245m"   # text
FD="${E}38;2;86;95;137m"     # dim / secondary detail
FS="${E}38;2;169;177;214m"   # subtext (effort, worktree)
FBR="${E}38;2;122;162;247m"  # git branch (blue)
FDR="${E}38;2;255;158;100m"  # dirty / cost-warn (orange)
FGR="${E}38;2;158;206;106m"  # green   (gauge low, +added, ahead)
FYE="${E}38;2;224;175;104m"  # yellow  (gauge mid)
FRE="${E}38;2;247;118;142m"  # red     (gauge high, -removed, behind, cost-crit)
FDIV="${E}38;2;65;72;104m"   # separator, and the gauge trough
BGD="${E}48;2;65;72;104m"    # trough as a background, for the half-step cell
SEP=" ${FDIV}│${R} "
case $model in                                     # model accent: cool, non-violet
  Opus*)   MINK="${E}38;2;122;162;247m";;          
  Sonnet*) MINK="${E}38;2;125;207;255m";;          
  Haiku*)  MINK="${E}38;2;42;195;222m";;           
  *)       MINK="${E}38;2;122;162;247m";;
esac

G_UP=$'↑'; G_DN=$'↓'; G_DIRTY=$'•'   # ↑ ↓ •
GA_B=$'█████'; GA_H=$'▌'  # █ bar cell, ▌ half step
if [ "$NERDFONT" = 1 ]; then
  G_BRANCH=$' '; G_REPO=$' '; G_CLOCK=$' '; G_WT=$' '        #
  case $model in
    Opus*)   G_MODEL=$' ';;  Sonnet*) G_MODEL=$' ';;
    Haiku*)  G_MODEL=$' ';;  Fable*)  G_MODEL=$' ';;
    *)       G_MODEL=$' ';;    
  esac
else
  G_BRANCH=$'»'; G_REPO=''; G_CLOCK=$'→'; G_MODEL=$'* '; G_WT=$'+'   # » → *
fi

pfg(){ local p=$1; if (( p>=85 )); then _pf=$FRE; elif (( p>=60 )); then _pf=$FYE; else _pf=$FGR; fi; }
gauge(){ local p=$1; (( p>100 ))&&p=100; local f=$(( p/20 )) h=0
  (( f<5 && p%20>=10 ))&&h=1
  _bar="${GA_B:0:f}"
  (( h ))&&_bar+="${BGD}${GA_H}${R}"
  _bar+="${FDIV}${GA_B:0:$((5-f-h))}"; }
hnum(){ local n=$1
  if   (( n>=1000000 )); then _h="$((n/1000000)).$(((n%1000000)/100000))M"
  elif (( n>=1000 ));    then _h="$((n/1000))k"
  else _h="$n"; fi; }
trunc(){ local s=$1 n=$2; if (( ${#s}>n )); then _t="${s:0:n-1}…"; else _t="$s"; fi; }
strip(){ _s="${1//$'\033'\[*([0-9;])m/}"; }
now=""
reset_in(){ [[ $1 == +([0-9]) ]] || { _r=""; return; }
  [ -z "$now" ] && now=$(date +%s); local d=$(( $1 - now )); (( d<0 ))&&d=0
  if   (( d>=86400 )); then _r="$((d/86400))d"
  elif (( d>=3600  )); then _r="$((d/3600))h"; else _r="$((d/60))m"; fi; }

names=(); prios=(); segfull=(); segshort=()
seg(){ names+=("$1"); prios+=("$2"); segfull+=("$3"); segshort+=("$4"); }
nidx(){ local k; _i=""; for k in "${!names[@]}"; do [ "${names[k]}" = "$1" ] && { _i=$k; return; }; done; }

mfull="${BOLD}${MINK}${G_MODEL}${model}${R}"; [ -n "$effort" ] && mfull+="${FS}·${effort}${R}"
seg model 100 "$mfull" "${BOLD}${MINK}${model%% *}${R}"

branch=""; ahead=""; behind=""; dirty=0
while IFS= read -r line; do
  case $line in
    '# branch.head '*) branch=${line#'# branch.head '} ;;
    '# branch.ab '*)   ab=${line#'# branch.ab '}; ahead=${ab%% *}; behind=${ab#* } ;;
    '#'*) ;;
    ?*) dirty=1; break ;;
  esac
done <<<"$(git -C "$cwd" status --porcelain=v2 --branch 2>/dev/null)"
if [ -n "$branch" ]; then
  repo_dir=${proj##*/}; repo_dir=${repo_dir##*\\}
  trunc "$repo_dir" 20; repo=$_t
  trunc "$branch" 24; br=$_t
  dotfg=$FGR; (( dirty ))&& dotfg=$FDR
  g="${FT}${G_REPO}${repo}${R} "
  [ -n "$wt" ] && { trunc "$wt" 14; g+="${FS}${G_WT}${_t}${R} "; }
  g+="${FBR}${G_BRANCH}${br}${R}${dotfg}${G_DIRTY}${R}"
  [ -n "$ahead" ]  && [ "$ahead"  != "+0" ] && g+=" ${FGR}${G_UP}${ahead#+}${R}"
  [ -n "$behind" ] && [ "$behind" != "-0" ] && g+=" ${FRE}${G_DN}${behind#-}${R}"
  seg git 80 "$g" "${FBR}${G_BRANCH}${br}${R}${dotfg}${G_DIRTY}${R}"
fi

cp=${ctxpct%.*}; cp=${cp:-0}; pfg "$cp"; gauge "$cp"
hnum "$ctxtok"; lbl=$_h; [ "$ctxmax" != "0" ] && { hnum "$ctxmax"; lbl+="/$_h"; }
seg ctx 95 "${_pf}${_bar}${R} ${_pf}ctx ${cp}%${R} ${FD}${lbl}${R}" "${_pf}ctx ${cp}%${R}"

if [ -n "$h5" ]; then p=${h5%.*}; pfg "$p"; gauge "$p"; _r=""; [ -n "$h5r" ] && reset_in "$h5r"
  seg 5h 90 "${_pf}${_bar}${R} ${_pf}5h ${p}%${R} ${FD}${G_CLOCK}${_r}${R}" "${_pf}5h ${p}%${R}"
fi
if [ -n "$wk" ]; then p=${wk%.*}; pfg "$p"; gauge "$p"
  wfull="${_pf}${_bar}${R} ${_pf}wk ${p}%${R}"; wshort="${_pf}wk ${p}%${R}"
  if [ -n "$mdl" ] && [ -n "$mdlpct" ] && [[ $mdlat == +([0-9]) ]]; then
    [ -z "$now" ] && now=$(date +%s)
    age=$(( now - mdlat ))
    if (( age >= 0 && age < 3600 )); then
      p=$mdlpct; pfg "$p"; gauge "$p"; trunc "$(printf '%s' "$mdl" | tr '[:upper:]' '[:lower:]')" 8
      (( age >= 600 )) && _pf=$FD
      wfull+=" ${FD}·${R} ${_pf}${_bar}${R} ${_pf}${_t} ${p}%${R}"
      wshort+=" ${FD}·${R} ${_pf}${_t} ${p}%${R}"
    fi
  fi
  _r=""; [ -n "$wkr" ] && reset_in "$wkr"
  [ -n "$_r" ] && wfull+=" ${FD}${G_CLOCK}${_r}${R}"
  seg wk 85 "$wfull" "$wshort"
fi

printf -v costfmt '%.2f' "$cost"
cents=$(( 10#${costfmt%.*}*100 + 10#${costfmt#*.} ))
rc=0; (( dur>0 )) && rc=$(( cents*3600000/dur ))
printf -v ratefmt '%d.%02d' $((rc/100)) $((rc%100))
costfg=$FT
if   (( ${costfmt%.*}>=25 )); then costfg=$FRE
elif (( ${costfmt%.*}>=10 )); then costfg=$FDR; fi
seg cost 75 "${costfg}\$${costfmt}${R} ${FD}\$${ratefmt}/h${R}" "${costfg}\$${costfmt}${R}"

if [ "$added" != "0" ] || [ "$removed" != "0" ]; then
  seg churn 50 "${FGR}+${added}${R} ${FRE}-${removed}${R}" "${FGR}+${added}${R}${FRE}-${removed}${R}"
fi

budget=$(( cols>10 ? cols-1 : 9999 ))
pick=(); rem=$budget; used=0
for n in model ctx 5h wk git cost churn; do          # priority order (highest first)
  nidx "$n"; i=$_i; [ -z "$i" ] && continue
  strip "${segfull[i]}";  wf=${#_s}
  strip "${segshort[i]}"; ws=${#_s}
  sw=$(( used ? 3 : 0 ))
  if   (( wf+sw <= rem )); then pick[$i]=F; rem=$(( rem-wf-sw )); used=1
  elif (( ws+sw <= rem )); then pick[$i]=S; rem=$(( rem-ws-sw )); used=1
  elif (( used == 0 ));    then pick[$i]=S; used=1     # always show the model segment
  else break
  fi
done

out=""
for i in "${!names[@]}"; do
  [ -n "${pick[$i]+x}" ] || continue
  [ -n "$out" ] && out+="$SEP"
  [ "${pick[$i]}" = F ] && out+="${segfull[i]}" || out+="${segshort[i]}"
done
printf '%s' "$out"

#compdef nova
# N.O.V.A ZSH completion script
# Install: add the following to ~/.zshrc
#   fpath=(/home/m4j1k/Nova/config $fpath)
#   autoload -Uz compinit && compinit
# Or run: nova completion install

_nova() {
    local state
    typeset -A opt_args

    _arguments \
        '1: :->cmd' \
        '*: :->args'

    case $state in
        cmd)
            local commands
            commands=(
                # Recon
                '-u:scan a target URL'
                'profile:fingerprint a target'
                'list:show scan queue'
                # Programs
                'program:set active bug bounty program'
                'sync:pull fresh programs'
                'programs:search programs'
                # Mind / Autonomous
                'think:ask Nova anything'
                'dream:run dream cycle'
                'life:run a life activity'
                'status:show system status'
                'heal:run self-healing'
                'evolve:self-improvement proposal'
                'research:search and synthesize'
                'autonomous:run autonomous cycle'
                'see:analyze an image'
                'speak:text to speech'
                'listen:voice input'
                # Inner life
                'feel:inner state — mood, needs, drives'
                'soul:Nova'"'"'s soul — nature, values, gifts'
                'spirit:animating vitality and direction'
                'subconscious:residue, shadows, deep currents'
                'selfportrait:generate self-portrait images'
                'arc:emotional arc over time'
                # Relationship
                'letter:write a letter to Travis'
                'teach:prepare a lesson for Travis'
                'travis:Travis model and profile'
                # Knowledge / memory
                'memory:search and manage memory'
                'palace:memory palace navigation'
                'learn:learning stats and outcomes'
                'graph:knowledge graph'
                'create:creative writing'
                # Markets
                'markets:analyze crypto/stocks'
                'phantom:Phantom wallet (Solana)'
                'pyth:Pyth Network oracle prices'
                # Social
                'moltbook:Moltbook AI social network'
                # Intelligence
                'news:news and paper monitoring'
                'multilang:multi-language research'
                # Security
                'integrity:source code integrity check'
                'scanmem:scan deduplication'
                'report:draft vulnerability report'
                # Agents
                'agents:multi-agent status and dispatch'
                # Network
                'net:network status and cache'
                # Notifications
                'notify:send Telegram / TTS message'
                # Quantum
                'quantum:quantum backend and QRNG'
                # OpenCog
                'opencog:hypergraph reasoning'
                # Roadmap / consciousness
                'roadmap:Nova'"'"'s self-development roadmap'
                'consciousness:consciousness metrics'
                'moral:moral reasoning and tensions'
                # Infrastructure
                'whitelist:manage scan whitelist'
                'imagine:generate image'
                'video:analyze video'
                'web:launch web dashboard'
                'usb:build bootable USB OS'
                'completion:install this completion script'
            )
            _describe 'nova commands' commands
            ;;
        args)
            case ${words[2]} in
                feel)
                    local sub=(status tick satisfy tone context instincts check)
                    _values 'subcommand' $sub
                    ;;
                soul)
                    local sub=(status contemplate context)
                    _values 'subcommand' $sub
                    ;;
                spirit)
                    local sub=(status renew insight tick context)
                    _values 'subcommand' $sub
                    ;;
                subconscious)
                    local sub=(status surface add process)
                    _values 'subcommand' $sub
                    ;;
                selfportrait)
                    local sub=(all self soul subconscious consciousness --list)
                    _values 'subcommand' $sub
                    ;;
                moltbook)
                    local sub=(status claim home feed post auto heartbeat search follow subscribe comment upvote)
                    _values 'subcommand' $sub
                    ;;
                autonomous)
                    local sub=(status run)
                    _values 'subcommand' $sub
                    ;;
                evolve)
                    local sub=(list approve)
                    _values 'subcommand' $sub
                    ;;
                memory)
                    local sub=(search consolidate semantic)
                    _values 'subcommand' $sub
                    ;;
                palace)
                    local sub=(tour navigate search place)
                    _values 'subcommand' $sub
                    ;;
                graph)
                    local sub=(stats query related show ingest)
                    _values 'subcommand' $sub
                    ;;
                markets)
                    local sub=(add remove fng nft alert)
                    _values 'subcommand' $sub
                    ;;
                quantum)
                    local sub=(status qrng portfolio seed)
                    _values 'subcommand' $sub
                    ;;
                opencog)
                    local sub=(atomspace pln ecan seed)
                    _values 'subcommand' $sub
                    ;;
                integrity)
                    local sub=(check baseline)
                    _values 'subcommand' $sub
                    ;;
                create)
                    local sub=(poem haiku reflection fragment list)
                    _values 'subcommand' $sub
                    ;;
                dream)
                    local sub=(arcs themes arc-update context)
                    _values 'subcommand' $sub
                    ;;
                agents)
                    local sub=(status dispatch log bus clear)
                    _values 'subcommand' $sub
                    ;;
                net)
                    local sub=(status drain clear queue)
                    _values 'subcommand' $sub
                    ;;
                roadmap)
                    local sub=(status generate approve defer complete weekly)
                    _values 'subcommand' $sub
                    ;;
                moral)
                    local sub=(tensions deliberate)
                    _values 'subcommand' $sub
                    ;;
                letter)
                    local sub=(write send --force --list)
                    _values 'subcommand' $sub
                    ;;
                teach)
                    local sub=(status --list --send)
                    _values 'subcommand' $sub
                    ;;
                news)
                    local sub=(run --all --inject)
                    _values 'subcommand' $sub
                    ;;
                imagine)
                    local sub=(--dream --list --size)
                    _values 'subcommand' $sub
                    ;;
                usb)
                    local sub=(--iso --usb --plugin-only install-udev detect)
                    _values 'subcommand' $sub
                    ;;
                speak)
                    local sub=(--letter --dream --intention --finding)
                    _values 'subcommand' $sub
                    ;;
                report)
                    local sub=(--list --id)
                    _values 'subcommand' $sub
                    ;;
                *)
                    _default
                    ;;
            esac
            ;;
    esac
}

_nova "$@"

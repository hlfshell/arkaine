function syntaxHighlightJson(json) {
    if (typeof json !== 'string') {
        try {
            json = JSON.stringify(json, null, 2);
        } catch (e) {
            return String(json); // Fallback for non-stringifiable objects
        }
    }
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        let cls = 'json-number';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'json-key';
            } else {
                cls = 'json-string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'json-boolean';
        } else if (/null/.test(match)) {
            cls = 'json-null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

export const EventView = {
    name: 'EventView',
    props: ['event', 'settings', 'context-id'],
    data() {
        return {
            isExpanded: true
        }
    },
    computed: {
        isMatch() {
            if (!this.$root.searchQuery) return false;
            const query = this.$root.searchQuery.toLowerCase();

            // Check event type
            if (this.event.type.toLowerCase().includes(query)) return true;

            // Check event data
            if (!this.event.data) return false;

            const searchInObject = (obj) => {
                if (typeof obj !== 'object') {
                    return String(obj).toLowerCase().includes(query);
                }

                for (let key in obj) {
                    const value = obj[key];
                    if (typeof value === 'object' && value !== null) {
                        if (searchInObject(value)) return true;
                    } else if (String(value).toLowerCase().includes(query)) {
                        return true;
                    }
                }
                return false;
            };

            let data = this.event.data;
            if (typeof data === 'string') {
                try {
                    data = JSON.parse(data);
                } catch (e) {
                    return data.toLowerCase().includes(query);
                }
            }

            return searchInObject(data);
        }
    },
    methods: {
        formatTimestamp(timestamp) {
            return new Date(timestamp * 1000).toLocaleString()
        },
        formatEventData(event) {
            if (!event.data) return ''

            try {
                let data = event.data;
                // Handle if data is already an object
                if (typeof data === 'object' && data !== null) {
                    switch (event.type) {
                        case 'agent_prompt':
                            return this.formatPromptData(data);
                        case 'agent_tool_calls':
                            return this.formatToolCallsData(data);
                        default:
                            return syntaxHighlightJson(data);
                    }
                }

                // Try to parse if it's a JSON string
                if (typeof data === 'string' && (data.startsWith('{') || data.startsWith('['))) {
                    try {
                        data = JSON.parse(data);
                        return syntaxHighlightJson(data);
                    } catch (e) {
                        // If parsing fails, use the original string
                        return data;
                    }
                }

                return String(data);
            } catch (e) {
                console.log('Error formatting event data:', e);
                return String(event.data);
            }
        },
        formatPromptData(data) {
            if (Array.isArray(data)) {
                return data.map(msg => `${msg.role}: ${msg.content}`).join('\n\n')
            }
            return JSON.stringify(data, null, 2)
        },
        formatToolCallsData(data) {
            try {
                if (typeof data === 'string') {
                    data = JSON.parse(data)
                }

                if (data.tool_calls) {
                    return data.tool_calls.map(call => {
                        if (Array.isArray(call)) {
                            // Handle the [name, args] format
                            const [name, args] = call
                            return `${name}(${JSON.stringify(args, null, 2)})`
                        } else {
                            // Handle object format
                            return `${call.name}(${JSON.stringify(call.args, null, 2)})`
                        }
                    }).join('\n\n')
                }
                return syntaxHighlightJson(data)
            } catch (e) {
                console.log('Error formatting tool calls:', e)
                return JSON.stringify(data, null, 2)
            }
        },
        copyEvent() {
            const eventJson = JSON.stringify(this.event, null, 2);
            navigator.clipboard.writeText(eventJson);
        }
    },
    template: `
        <li :class="['event', { highlight: isMatch }]">
            <div class="event-header" @click="isExpanded = !isExpanded">
                <span class="collapse-icon">{{ isExpanded ? '−' : '+' }}</span>
                <span class="event-type">{{ event.type }}</span>
                <span class="event-timestamp">{{ formatTimestamp(event.timestamp) }}</span>
            </div>
            <button class="copy-button" @click.stop="copyEvent">📋</button>
            <div :class="['event-content', { collapsed: !isExpanded }]">
                <div v-if="event.data" class="event-data">
                    <pre v-html="formatEventData(event)"></pre>
                </div>
            </div>
        </li>
    `,
    mounted() {
        window.addEventListener('updateExpansion', (e) => {
            if (e.detail.contextId === this.contextId) {
                this.isExpanded = e.detail.expanded;
            }
        });
    },
    unmounted() {
        window.removeEventListener('updateExpansion', this.handleExpansion);
    }
}
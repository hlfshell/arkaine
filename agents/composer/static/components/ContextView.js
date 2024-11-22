import { EventView } from './EventView.js';

// Add syntaxHighlightJson function at the top level
function syntaxHighlightJson(obj) {
    if (typeof obj !== 'string') {
        obj = JSON.stringify(obj, null, 2);
    }
    return obj.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
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

export const ContextView = {
    name: 'ContextView',
    components: {
        EventView
    },
    props: ['context', 'settings', 'depth', 'contexts', 'searchQuery'],
    data() {
        return {
            isExpanded: true,
            isEventsExpanded: false,  // Events section starts collapsed
            isOutputExpanded: true,    // Output section starts expanded
            isChildrenExpanded: true  // Add new state for children section
        }
    },
    methods: {
        getChildContexts(parentId) {
            if (!this.contexts) return [];
            if (this.context.children && this.context.children.length > 0) {
                return this.context.children.sort((a, b) => (a.created_at || 0) - (b.created_at || 0));
            }
            return Array.from(this.contexts.values())
                .filter(context => context.parent_id === parentId)
                .sort((a, b) => (a.created_at || 0) - (b.created_at || 0));
        },
        copyContext() {
            const events = this.getEvents();

            const childContexts = this.getChildContexts(this.context.id);

            const contextData = {
                id: this.context.id,
                tool_name: this.context.tool_name,
                parent_id: this.context.parent_id,
                status: this.context.status,
                output: this.context.output,
                error: this.context.error,
                created_at: this.context.created_at,
                events: events,
                children: childContexts,
            };
            navigator.clipboard.writeText(JSON.stringify(contextData, null, 2));
        },
        formatOutput(output) {
            if (!output) return '';
            try {
                let formatted = '';
                if (typeof output === 'string') {
                    // Try to parse if it looks like JSON
                    if (output.trim().startsWith('{') || output.trim().startsWith('[')) {
                        try {
                            const parsed = JSON.parse(output);
                            formatted = syntaxHighlightJson(parsed);
                        } catch {
                            formatted = output;
                        }
                    } else {
                        formatted = output;
                    }
                } else {
                    formatted = syntaxHighlightJson(output);
                }

                return formatted;
            } catch (e) {
                return String(output);
            }
        },
        formatTimestamp(timestamp) {
            if (!timestamp) return 'N/A';
            return new Date(timestamp * 1000).toLocaleString();
        },
        getCreationTime() {
            if (this.context.events) {
                const createdEvent = this.context.events.find(e => e.type === 'context_created');
                if (createdEvent) {
                    return createdEvent.data.timestamp;
                }
                if (this.context.events.length > 0) {
                    return Math.min(...this.context.events.map(e => e.timestamp));
                }
            }
            return null;
        },
        getLastEventTime() {
            if (this.context.events && this.context.events.length > 0) {
                return Math.max(...this.context.events.map(e => e.timestamp));
            }
            return null;
        },
        handleContextEvent(event) {
            switch (event.type) {
                case 'context_update':
                    // Handle context updates (e.g., name changes)
                    if (event.data.name) {
                        this.context.name = event.data.name;
                    }
                    break;

                case 'context_exception':
                    // Handle context exceptions
                    this.context.status = 'error';
                    this.context.error = event.data;
                    break;

                case 'context_output':
                    // Handle context output updates
                    this.context.output = event.data;
                    this.context.status = 'success';
                    break;
            }
        },
        expandAllEvents() {
            this.isEventsExpanded = true;
            // Set all events in this context to expanded
            window.dispatchEvent(new CustomEvent('updateExpansion', {
                detail: {
                    expanded: true,
                    contextId: this.context.id
                }
            }));
        },
        collapseAllEvents() {
            this.isEventsExpanded = false;
            // Set all events in this context to collapsed
            window.dispatchEvent(new CustomEvent('updateExpansion', {
                detail: {
                    expanded: false,
                    contextId: this.context.id
                }
            }));
        },
        copyOutput() {
            const output = this.context.output;
            if (typeof output === 'object') {
                navigator.clipboard.writeText(JSON.stringify(output, null, 2));
            } else {
                navigator.clipboard.writeText(String(output));
            }
        },
        getEvents() {
            let events = (this.context.events || []).filter(event =>
                !['context_update'].includes(event.type)
            );

            if (this.searchQuery?.trim()) {
                const searchTerm = this.searchQuery.trim().toLowerCase();
                events = events.filter(event => {
                    const eventData = JSON.stringify(event.data).toLowerCase();
                    return eventData.includes(searchTerm);
                });
            }

            return events;
        },
        getCombinedTimelineItems() {
            const events = this.getEvents().map(event => ({
                type: 'event',
                timestamp: event.timestamp,
                data: event
            }));

            const childContexts = this.getChildContexts(this.context.id).map(context => ({
                type: 'context',
                timestamp: context.created_at,
                data: context
            }));

            return [...events, ...childContexts].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        },
        isMatch() {
            if (!this.$root.searchQuery) return false;
            const query = this.$root.searchQuery.toLowerCase();

            if (!this.context.output) return false;
            return this.context.output.trim().toLowerCase().includes(query);
        },
        shouldShowContext() {
            if (!this.searchQuery?.trim()) return true;

            const searchTerm = this.searchQuery.trim().toLowerCase();

            // Check output
            const output = this.context.output;
            const outputStr = typeof output === 'object' ?
                JSON.stringify(output) : String(output || '');
            if (outputStr.toLowerCase().includes(searchTerm)) {
                return true;
            }

            // Check events
            if (this.context.events?.some(event =>
                JSON.stringify(event.data).toLowerCase().includes(searchTerm)
            )) {
                return true;
            }

            // Check error
            if (this.context.error?.toLowerCase().includes(searchTerm)) {
                return true;
            }

            // Check tool name
            if (this.context.tool_name?.toLowerCase().includes(searchTerm)) {
                return true;
            }

            return false;
        }
    },
    template: `
        <div v-if="shouldShowContext()" class="context-container">
            <div class="context-header">
                <span :class="['status', 'status-' + context.status]">{{ context.status }}</span>
                <div class="context-id-section">
                    <button class="collapse-button" @click="isExpanded = !isExpanded">
                        <span class="collapse-icon"><b>{{ isExpanded ? '−' : '+' }}</b></span>
                        <span class="tool-name" v-if="context.tool_name">{{ context.tool_name }}</span>
                        <span class="context-id" v-else>Context {{ context.id }}</span>
                    </button>
                    <span class="context-timestamps">
                        Created: {{ formatTimestamp(context.created_at) }}
                    </span>
                </div>
                <button class="copy-button" @click.stop="copyContext">📋</button>
            </div>
            <div v-if="isExpanded">
                <!-- Combined timeline section -->
                <div v-if="getCombinedTimelineItems().length > 0" class="context-section">
                    <div class="section-header" @click="isEventsExpanded = !isEventsExpanded" style="cursor: pointer;">
                        <span>Timeline ({{ getCombinedTimelineItems().length }})</span>
                        <div style="display: flex; gap: 10px;">
                            <button @click.stop="expandAllEvents" class="action-button" style="padding: 2px 8px;"><b>+</b></button>
                            <button @click.stop="collapseAllEvents" class="action-button" style="padding: 2px 8px;"><b>−</b></button>
                        </div>
                    </div>
                    <ul v-show="isEventsExpanded" class="event-list">
                        <template v-for="item in getCombinedTimelineItems()" :key="item.timestamp">
                            <event-view
                                v-if="item.type === 'event'"
                                :event="item.data"
                                :settings="settings"
                                :context-id="context.id"
                                :search-query="searchQuery"
                            ></event-view>
                            <context-view
                                v-else
                                :context="item.data"
                                :contexts="contexts"
                                :settings="settings"
                                :depth="depth + 1"
                                :search-query="searchQuery"
                            ></context-view>
                        </template>
                    </ul>
                </div>

                <!-- Error section -->
                <div v-if="context.error" class="context-section error-section">
                    <div class="section-header">
                        <span>Error</span>
                    </div>
                    <pre class="error-content">{{ context.error }}</pre>
                </div>

                <!-- Child contexts section -->
                <div v-if="getChildContexts(context.id).length > 0" class="context-section">
                    <div class="section-header" @click="isChildrenExpanded = !isChildrenExpanded" style="cursor: pointer;">
                        <span>Tools Used ({{ getChildContexts(context.id).length }})</span>
                        <div style="display: flex; gap: 10px;">
                            <button @click.stop="isChildrenExpanded = true" class="action-button" style="padding: 2px 8px;"><b>+</b></button>
                            <button @click.stop="isChildrenExpanded = false" class="action-button" style="padding: 2px 8px;"><b>−</b></button>
                        </div>
                    </div>
                    <div v-show="isChildrenExpanded" class="child-contexts">
                        <context-view
                            v-for="childContext in getChildContexts(context.id)"
                            :key="childContext.id"
                            :context="childContext"
                            :contexts="contexts"
                            :settings="settings"
                            :depth="depth + 1"
                            :search-query="searchQuery"
                        ></context-view>
                    </div>
                </div>

                <!-- Output section -->
                <div v-if="context.output" class="context-section" :class="{ highlight: isMatch }">
                    <div class="section-header" @click="isOutputExpanded = !isOutputExpanded" style="cursor: pointer;">
                        <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                            <span>Output</span>
                            <button class="copy-button" @click.stop="copyOutput">📋</button>
                        </div>
                    </div>
                    <pre v-show="isOutputExpanded" v-html="formatOutput(context.output)"></pre>
                </div>
            </div>
        </div>
    `
}
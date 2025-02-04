import { DataView } from './DataView.js';
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
        EventView,
        DataView
    },
    props: ['context', 'settings', 'depth', 'contexts', 'searchQuery'],
    data() {
        return {
            isExpanded: false,
            isEventsExpanded: false,
            isOutputExpanded: true,
            isToolsExpanded: false,
            isLLMsExpanded: false,
            isArgsExpanded: true,
            isDataExpanded: false,
            isXExpanded: false,
            isDebugExpanded: false,
        }
    },
    computed: {
        showTimelineOnly() {
            return this.settings.viewMode === 'timeline';
        },
        showRetryButton() {
            return !this.context.parent_id && this.context.error;
        }
    },
    methods: {
        copyContext() {
            const events = this.getEvents();

            const childContexts = this.context.children;

            const contextData = {
                id: this.context.id,
                attached_id: this.context.attached_id,
                attached_name: this.context.attached_name,
                attached_type: this.context.attached_type,
                parent_id: this.context.parent_id,
                status: this.context.status,
                output: this.context.output,
                error: this.context.error,
                created_at: this.context.created_at,
                events: events,
                children: childContexts,
                data: this.context.data,
                x: this.context.x,
                debug: this.context.debug,
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

            const childContexts = (this.context.children || []).map(child => ({
                type: 'context',
                timestamp: child.created_at,
                data: child
            }));

            return [...events, ...childContexts].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        },
        isMatch() {
            const query = this.searchQuery?.trim().toLowerCase();
            if (!query) return false;

            // Check output
            if (this.context.output) {
                const outputStr = typeof this.context.output === 'object' ?
                    JSON.stringify(this.context.output) : String(this.context.output);
                if (outputStr.toLowerCase().includes(query)) return true;
            }

            // Check args
            if (this.context.args) {
                const argsStr = typeof this.context.args === 'object' ?
                    JSON.stringify(this.context.args) : String(this.context.args);
                if (argsStr.toLowerCase().includes(query)) return true;
            }

            // Check events
            if (this.context.events?.some(event => {
                const eventStr = JSON.stringify(event.data).toLowerCase();
                return eventStr.includes(query);
            })) return true;

            return false;
        },
        shouldShowContext() {
            if (!this.searchQuery?.trim()) return true;

            const searchTerm = this.searchQuery.trim().toLowerCase();

            // Check tool name
            if (this.context.tool_name?.toLowerCase().includes(searchTerm)) return true;

            // Check output
            if (this.context.output) {
                const outputStr = typeof this.context.output === 'object' ?
                    JSON.stringify(this.context.output) : String(this.context.output);
                if (outputStr.toLowerCase().includes(searchTerm)) return true;
            }

            // Check args
            if (this.context.args) {
                const argsStr = typeof this.context.args === 'object' ?
                    JSON.stringify(this.context.args) : String(this.context.args);
                if (argsStr.toLowerCase().includes(searchTerm)) return true;
            }

            // Check events
            if (this.context.events?.some(event => {
                const eventStr = JSON.stringify(event.data).toLowerCase();
                return eventStr.includes(searchTerm);
            })) return true;

            // Check error
            if (this.context.error?.toLowerCase().includes(searchTerm)) return true;

            return false;
        },
        isErrorMatch() {
            const query = this.searchQuery?.trim().toLowerCase();
            if (!query) return false;

            if (!this.context.error) return false;
            return this.context.error.toLowerCase().includes(query);
        },
        shouldShowData() {
            const hasData = this.context.data && Object.keys(this.context.data).length > 0;
            const hasX = this.context.x && Object.keys(this.context.x).length > 0;
            const hasDebug = this.context.debug && Object.keys(this.context.debug).length > 0;
            return hasData || hasX || hasDebug;
        },
        retryContext() {
            // Emit event to be handled by parent app
            this.$emit('retry-context', this.context.id);
        }
    },
    template: `
        <div v-if="shouldShowContext()" class="context-container">
            <div class="context-header">
                <span :class="['status', 'status-' + context.status]">{{ context.status }}</span>
                <div class="context-id-section">
                    <button class="collapse-button" @click="isExpanded = !isExpanded">
                        <span class="collapse-icon"><b>{{ isExpanded ? '−' : '+' }}</b></span>
                        <span class="tool-name" v-if="context.attached_name">{{ context.attached_name }}</span>
                        <span class="context-id" v-else>Context {{ context.id }}</span>
                        <span class="context-timestamps">
                            Created: {{ formatTimestamp(context.created_at) }}
                        </span>
                    </button>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button v-if="showRetryButton" class="retry-button" @click.stop="retryContext" title="Retry">↻</button>
                    <button class="copy-button" @click.stop="copyContext">📋</button>
                </div>
            </div>

            <!-- Arguments Section -->
            <div v-if="context.args && isExpanded" class="context-section">
                <div class="section-header" @click="isArgsExpanded = !isArgsExpanded" style="cursor: pointer;">
                    <span>Arguments</span>
                    <span class="expand-icon">{{ isArgsExpanded ? '−' : '+' }}</span>
                </div>
                <div v-show="isArgsExpanded" class="section-content">
                    <pre v-html="formatOutput(context.args)"></pre>
                </div>
            </div>

            <div v-if="isExpanded">
                <!-- Combined timeline section -->
                <div v-if="showTimelineOnly && getCombinedTimelineItems().length > 0" class="context-section">
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

                <!-- Child contexts section - only show in separate view -->
                <div v-if="!showTimelineOnly && context.children && context.children.filter(child => child.attached_type === 'tool').length > 0" class="context-section">
                    <div class="section-header" @click="isToolsExpanded = !isToolsExpanded" style="cursor: pointer;">
                        <span>Children ({{ context.children.filter(child => child.attached_type === 'tool').length }})</span>
                        <div style="display: flex; gap: 10px;">
                            <button @click.stop="isToolsExpanded = true" class="action-button" style="padding: 2px 8px;"><b>+</b></button>
                            <button @click.stop="isToolsExpanded = false" class="action-button" style="padding: 2px 8px;"><b>−</b></button>
                        </div>
                    </div>
                    <div v-show="isToolsExpanded" class="child-contexts">
                        <context-view
                            v-for="childContext in context.children.filter(child => child.attached_type === 'tool')"
                            :key="childContext.id"
                            :context="childContext"
                            :contexts="contexts"
                            :settings="settings"
                            :depth="depth + 1"
                            :search-query="searchQuery"
                        ></context-view>
                    </div>
                </div>

                <!-- LLM Calls section - only show in separate view -->
                <div v-if="!showTimelineOnly && context.children && context.children.filter(child => child.attached_type === 'llm').length > 0" class="context-section">
                    <div class="section-header" @click="isLLMsExpanded = !isLLMsExpanded" style="cursor: pointer;">
                        <span>LLM Calls ({{ context.children.filter(child => child.attached_type === 'llm').length }})</span>
                        <div style="display: flex; gap: 10px;">
                            <button @click.stop="isLLMsExpanded = true" class="action-button" style="padding: 2px 8px;"><b>+</b></button>
                            <button @click.stop="isLLMsExpanded = false" class="action-button" style="padding: 2px 8px;"><b>−</b></button>
                        </div>
                    </div>
                    <div v-show="isLLMsExpanded" class="child-contexts">
                        <context-view
                            v-for="childContext in context.children.filter(child => child.attached_type === 'llm')"
                            :key="childContext.id"
                            :context="childContext"
                            :contexts="contexts"
                            :settings="settings"
                            :depth="depth + 1"
                            :search-query="searchQuery"
                        ></context-view>
                    </div>
                </div>

                <!-- Events section - only show in separate view -->
                <div v-if="!showTimelineOnly && getEvents().length > 0" class="context-section">
                    <div class="section-header" @click="isEventsExpanded = !isEventsExpanded" style="cursor: pointer;">
                        <span>Events ({{ getEvents().length }})</span>
                        <div style="display: flex; gap: 10px;">
                            <button @click.stop="expandAllEvents" class="action-button" style="padding: 2px 8px;"><b>+</b></button>
                            <button @click.stop="collapseAllEvents" class="action-button" style="padding: 2px 8px;"><b>−</b></button>
                        </div>
                    </div>
                    <ul v-show="isEventsExpanded" class="event-list">
                        <event-view
                            v-for="event in getEvents()"
                            :key="event.timestamp"
                            :event="event"
                            :settings="settings"
                            :context-id="context.id"
                            :search-query="searchQuery"
                        ></event-view>
                    </ul>
                </div>

                <!-- Data Section -->
                <div v-if="shouldShowData()" class="context-section">
                    <div class="section-header" @click="isDataExpanded = !isDataExpanded" style="cursor: pointer;">
                        <span>Data</span>
                        <span class="expand-icon">{{ isDataExpanded ? '−' : '+' }}</span>
                    </div>
                    <div v-show="isDataExpanded" class="section-content">
                        <!-- Data Store -->
                        <data-view
                            v-if="context.data"
                            :data="context.data"
                            title="Data"
                        ></data-view>

                        <!-- Shared Data (x) -->
                        <data-view
                            v-if="context.x"
                            :data="context.x"
                            title="Execution Data (x)"
                        ></data-view>

                        <!-- Debug Data -->
                        <data-view
                            v-if="context.debug"
                            :data="context.debug"
                            title="Debug Data"
                        ></data-view>
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

                <!-- Error section -->
                <div v-if="context.error" class="context-section error-section" :class="{ highlight: isErrorMatch() }">
                    <div class="section-header">
                        <span>Error</span>
                    </div>
                    <pre class="error-content">{{ context.error }}</pre>
                </div>
            </div>
        </div>
    `
}
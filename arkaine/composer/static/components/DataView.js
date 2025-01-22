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

export const DataView = {
    name: 'DataView',
    props: ['data', 'title'],
    data() {
        return {
            isExpanded: true,
        }
    },
    computed: {
        hasData() {
            return this.data && Object.keys(this.data).length > 0;
        }
    },
    methods: {
        formatValue(value) {
            if (value === null) return 'null';
            if (value === undefined) return 'undefined';

            try {
                if (typeof value === 'object' && data !== null) {
                    return syntaxHighlightJson(value);
                } else if (typeof value === 'string' && (value.startsWith('{') || value.startsWith('['))) {
                    return syntaxHighlightJson(JSON.parse(value));
                }
                return String(value);
            } catch (e) {
                return String(value);
            }
        }
    },
    template: `
        <div v-if="hasData" class="data-store-section">
            <div class="section-header" @click="isExpanded = !isExpanded" style="cursor: pointer;">
                <span>{{ title }}</span>
                <span class="expand-icon">{{ isExpanded ? '−' : '+' }}</span>
            </div>
            <div v-show="isExpanded" class="data-store-content">
                <table class="data-store-table">
                    <tbody>
                        <tr v-for="(value, key) in data" :key="key">
                            <td class="key-cell">{{ key }}</td>
                            <td class="value-cell">
                                <pre v-html="formatValue(value)"></pre>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `
}
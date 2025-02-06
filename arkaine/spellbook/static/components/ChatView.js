const { ref, onMounted, onUnmounted } = Vue;

export const ChatView = {
    name: 'ChatView',
    props: ['chat'],
    setup(props, { emit }) {
        // Local list of messages shown in the chat
        const messages = ref([]);
        const userInput = ref('');

        // When user presses "Send" or hits enter
        function sendMessage() {
            if (!userInput.value.trim()) return;

            // Add the user message to local chat
            messages.value.push({
                sender: 'User',
                content: userInput.value
            });

            // Emit an event so the parent can call the chat's tool
            // (the parent typically calls "executeProducer" in app.js)
            emit('send-message', {
                attached_id: props.chat.id,
                attached_type: props.chat.type, // "chat"
                args: { message: userInput.value }
            });

            userInput.value = '';
        }

        // A function to handle new contexts from the server (the agent's response).
        function handleChatMessageIncoming(e) {
            const ctx = e.detail;
            if (ctx.attached_id === props.chat.id) {
                // We'll treat the context's output as the agent's reply
                if (ctx.output) {
                    messages.value.push({
                        sender: props.chat.name || 'Agent',
                        content: ctx.output
                    });
                }
                // If there's an error, also show it
                if (ctx.error) {
                    messages.value.push({
                        sender: '(Error)',
                        content: ctx.error
                    });
                }
            }
        }

        onMounted(() => {
            // Listen for new contexts for "chat" from app.js
            window.addEventListener(
                'chat_message_incoming',
                handleChatMessageIncoming
            );
        });

        onUnmounted(() => {
            window.removeEventListener(
                'chat_message_incoming',
                handleChatMessageIncoming
            );
        });

        return {
            messages,
            userInput,
            sendMessage
        };
    },
    template: `
        <div class="chat-view">

            <!-- "Back" button, same style as other views -->
            <button class="back-button" @click="$emit('back')">&larr; Back</button>

            <h2 class="chat-header">{{ chat.name || 'Chat Agent' }}</h2>

            <div class="chat-messages">
                <div 
                    v-for="(msg, index) in messages" 
                    :key="index"
                    :class="['chat-message', msg.sender === 'User' ? 'chat-message-user' : 'chat-message-agent']"
                >
                    <div class="chat-sender">{{ msg.sender }}</div>
                    <div class="chat-content">{{ msg.content }}</div>
                </div>
            </div>

            <div class="chat-input-container">
                <textarea
                    class="chat-textarea"
                    v-model="userInput"
                    rows="3"
                    placeholder="Type a message..."
                    @keydown.ctrl.enter.prevent="sendMessage"
                ></textarea>
                <button class="chat-send-button" @click="sendMessage">Send</button>
            </div>
        </div>
    `
};
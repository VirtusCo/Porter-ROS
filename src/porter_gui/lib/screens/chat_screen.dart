// Copyright 2026 VirtusCo
// Licensed under Apache-2.0

import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/models.dart';
import '../providers/providers.dart';
import '../theme/porter_theme.dart';

/// AI Chat screen — Perplexity-inspired centered layout.
///
/// Empty state: large centered "Virtue" brand + search bar + suggestion chips.
/// Conversation state: clean messages + bottom input bar.
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode();
  bool _scrollScheduled = false;

  /// Quick action suggestions shown on empty state.
  static const List<_SuggestionItem> _suggestions = [
    _SuggestionItem(Icons.flight, 'Flight status'),
    _SuggestionItem(Icons.restaurant, 'Restaurants'),
    _SuggestionItem(Icons.wc, 'Restrooms'),
    _SuggestionItem(Icons.luggage, 'Luggage help'),
    _SuggestionItem(Icons.wifi, 'Wi-Fi info'),
    _SuggestionItem(Icons.map_outlined, 'Gate directions'),
  ];

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _sendMessage(ChatProvider chat) {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    chat.sendMessage(text);
    _controller.clear();
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// Debounced auto-scroll for streaming — only if already near bottom.
  void _scheduleAutoScroll() {
    if (_scrollScheduled) return;
    _scrollScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollScheduled = false;
      if (_scrollController.hasClients) {
        final pos = _scrollController.position;
        // Only auto-scroll if user is near the bottom (within 150px).
        if (pos.maxScrollExtent - pos.pixels < 150) {
          _scrollController.jumpTo(pos.maxScrollExtent);
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final chat = context.watch<ChatProvider>();
    final hasMessages = chat.messages.isNotEmpty;

    // Auto-scroll when messages change (new message or streaming update).
    if (hasMessages) {
      _scheduleAutoScroll();
    }

    return Column(
      children: [
        _buildTopBar(chat),
        Expanded(
          child: hasMessages ? _buildConversation(chat) : _buildWelcome(chat),
        ),
        if (hasMessages) _buildInputBar(chat),
      ],
    );
  }

  /// Minimal top bar with AI status badge and clear button.
  Widget _buildTopBar(ChatProvider chat) {
    return Container(
      height: 40,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          // AI status dot + label.
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: chat.aiServerAvailable
                  ? PorterTheme.successGreen.withValues(alpha: 0.12)
                  : PorterTheme.emergencyRed.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    color: chat.aiServerAvailable
                        ? PorterTheme.successGreen
                        : PorterTheme.emergencyRed,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  chat.aiServerAvailable ? 'Online' : 'Offline',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: chat.aiServerAvailable
                        ? PorterTheme.successGreen
                        : PorterTheme.emergencyRed,
                  ),
                ),
              ],
            ),
          ),
          const Spacer(),
          if (chat.messages.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.delete_outline,
                  size: 18, color: PorterTheme.textTertiary),
              onPressed: chat.clearMessages,
              tooltip: 'Clear conversation',
              style: IconButton.styleFrom(
                minimumSize: const Size(36, 36),
              ),
            ),
        ],
      ),
    );
  }

  /// Welcome / empty state — centered branding + search + suggestions.
  Widget _buildWelcome(ChatProvider chat) {
    return Center(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Brand icon.
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [PorterTheme.primaryBlue, PorterTheme.accentCyan],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Icon(Icons.smart_toy_rounded,
                    color: Colors.white, size: 28),
              ),
              const SizedBox(height: 16),
              // Brand name.
              const Text(
                'Virtue',
                style: TextStyle(
                  fontSize: 32,
                  fontWeight: FontWeight.w700,
                  color: PorterTheme.textPrimary,
                  letterSpacing: -1,
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                'Your airport assistant',
                style: TextStyle(
                  fontSize: 15,
                  color: PorterTheme.textSecondary,
                ),
              ),
              const SizedBox(height: 28),

              // Search-style input.
              Container(
                constraints: const BoxConstraints(maxWidth: 500),
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  style: const TextStyle(
                      fontSize: 15, color: PorterTheme.textPrimary),
                  decoration: InputDecoration(
                    hintText: 'Ask anything...',
                    prefixIcon: const Padding(
                      padding: EdgeInsets.only(left: 16, right: 8),
                      child: Icon(Icons.search,
                          color: PorterTheme.textTertiary, size: 20),
                    ),
                    prefixIconConstraints:
                        const BoxConstraints(minWidth: 0, minHeight: 0),
                    suffixIcon: Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: IconButton(
                        icon: const Icon(Icons.arrow_upward_rounded,
                            size: 20, color: Colors.white),
                        style: IconButton.styleFrom(
                          backgroundColor: PorterTheme.primaryBlue,
                          minimumSize: const Size(36, 36),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: chat.isResponding
                            ? null
                            : () => _sendMessage(chat),
                      ),
                    ),
                    suffixIconConstraints:
                        const BoxConstraints(minWidth: 0, minHeight: 0),
                    filled: true,
                    fillColor: PorterTheme.surfaceCard,
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 16),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(28),
                      borderSide:
                          const BorderSide(color: PorterTheme.surfaceBorder),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(28),
                      borderSide:
                          const BorderSide(color: PorterTheme.surfaceBorder),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(28),
                      borderSide: const BorderSide(
                          color: PorterTheme.accentCyan, width: 1.5),
                    ),
                  ),
                  onSubmitted: (_) => _sendMessage(chat),
                ),
              ),
              const SizedBox(height: 20),

              // Suggestion chips.
              Container(
                constraints: const BoxConstraints(maxWidth: 500),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: _suggestions.map((s) {
                    return _SuggestionChip(
                      icon: s.icon,
                      label: s.label,
                      onTap: () {
                        _controller.text = s.label;
                        _sendMessage(chat);
                      },
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Conversation view — messages list.
  Widget _buildConversation(ChatProvider chat) {
    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      addAutomaticKeepAlives: false,
      itemCount: chat.messages.length + (chat.isResponding ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == chat.messages.length && chat.isResponding) {
          return const _TypingIndicator();
        }
        final msg = chat.messages[index];
        return _MessageBubble(
          message: msg,
          index: index,
          totalMessages: chat.messages.length,
        );
      },
    );
  }

  /// Bottom input bar (shown during conversation).
  Widget _buildInputBar(ChatProvider chat) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
      decoration: const BoxDecoration(
        border: Border(
          top: BorderSide(color: PorterTheme.surfaceBorder),
        ),
      ),
      child: Container(
        decoration: BoxDecoration(
          color: PorterTheme.surfaceCard,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: PorterTheme.surfaceBorder),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                focusNode: _focusNode,
                style: const TextStyle(
                    fontSize: 14, color: PorterTheme.textPrimary),
                decoration: const InputDecoration(
                  hintText: 'Ask Virtue...',
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  contentPadding:
                      EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                ),
                onSubmitted: (_) => _sendMessage(chat),
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: IconButton(
                icon: const Icon(Icons.arrow_upward_rounded,
                    size: 20, color: Colors.white),
                style: IconButton.styleFrom(
                  backgroundColor: chat.isResponding
                      ? PorterTheme.textTertiary
                      : PorterTheme.primaryBlue,
                  minimumSize: const Size(36, 36),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                onPressed:
                    chat.isResponding ? null : () => _sendMessage(chat),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Data class for suggestion items.
class _SuggestionItem {
  final IconData icon;
  final String label;
  const _SuggestionItem(this.icon, this.label);
}

/// Pill-shaped suggestion chip.
class _SuggestionChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _SuggestionChip({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: PorterTheme.surfaceCard,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: PorterTheme.surfaceBorder),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 16, color: PorterTheme.textSecondary),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  fontSize: 13,
                  color: PorterTheme.textPrimary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Single chat message — handles tool_call rendering and streaming text.
class _MessageBubble extends StatelessWidget {
  final ChatMessage message;
  final int index;
  final int totalMessages;

  const _MessageBubble({
    required this.message,
    required this.index,
    required this.totalMessages,
  });

  @override
  Widget build(BuildContext context) {
    if (message.isUser) return _buildUserBubble(context);
    return _buildAiBubble(context);
  }

  Widget _buildUserBubble(BuildContext context) {
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.6,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: const BoxDecoration(
          color: PorterTheme.primaryBlue,
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(18),
            topRight: Radius.circular(18),
            bottomLeft: Radius.circular(18),
            bottomRight: Radius.circular(4),
          ),
        ),
        child: Text(
          message.text,
          style: const TextStyle(
            fontSize: 14,
            height: 1.4,
            color: Colors.white,
          ),
        ),
      ),
    );
  }

  Widget _buildAiBubble(BuildContext context) {
    final hasToolCalls = message.toolCalls.isNotEmpty;
    final hasText = message.text.isNotEmpty;
    final isDone = !message.isStreaming;
    final isLastAi = index == totalMessages - 1;

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.75,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (hasToolCalls)
              _ThinkingShimmer(
                toolCalls: message.toolCalls,
                isActive: message.isStreaming,
              ),
            if (hasToolCalls && hasText) const SizedBox(height: 10),
            if (hasText)
              SelectableText(
                message.text,
                style: const TextStyle(
                  fontSize: 14,
                  height: 1.5,
                  color: PorterTheme.textPrimary,
                ),
              ),
            if (message.isStreaming && !hasText && hasToolCalls)
              const Padding(
                padding: EdgeInsets.only(top: 8),
                child: _StreamingCursor(),
              ),
            // Feedback row — shown when streaming is done.
            if (isDone && (hasText || hasToolCalls))
              _FeedbackRow(
                message: message,
                showRegenerate: isLastAi,
              ),
          ],
        ),
      ),
    );
  }
}

/// Collapsible "Thinking" section with shimmer effect for tool_call blocks.
class _ThinkingShimmer extends StatefulWidget {
  final List<String> toolCalls;
  final bool isActive;

  const _ThinkingShimmer({
    required this.toolCalls,
    required this.isActive,
  });

  @override
  State<_ThinkingShimmer> createState() => _ThinkingShimmerState();
}

class _ThinkingShimmerState extends State<_ThinkingShimmer>
    with SingleTickerProviderStateMixin {
  late AnimationController _shimmerController;
  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    _shimmerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    if (widget.isActive) {
      _shimmerController.repeat();
    }
  }

  @override
  void didUpdateWidget(covariant _ThinkingShimmer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isActive && !_shimmerController.isAnimating) {
      _shimmerController.repeat();
    } else if (!widget.isActive && _shimmerController.isAnimating) {
      _shimmerController.stop();
      _shimmerController.value = 0;
    }
  }

  @override
  void dispose() {
    _shimmerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () => setState(() => _expanded = !_expanded),
            child: AnimatedBuilder(
              animation: _shimmerController,
              builder: (context, child) {
                return ShaderMask(
                  shaderCallback: (bounds) {
                    if (!widget.isActive) {
                      return const LinearGradient(
                        colors: [Color(0xFF9B9B9B), Color(0xFF9B9B9B)],
                      ).createShader(bounds);
                    }
                    final v = _shimmerController.value;
                  return LinearGradient(
                    begin: Alignment(v * 4 - 2, 0),
                    end: Alignment(v * 4 - 0.5, 0),
                    colors: const [
                      Color(0xFF6B6B6B),
                      Color(0xFFCCCCCC),
                      Color(0xFF6B6B6B),
                    ],
                  ).createShader(bounds);
                },
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.auto_awesome,
                        size: 14, color: Colors.white),
                    const SizedBox(width: 6),
                    Text(
                      widget.isActive ? 'Thinking...' : 'Thought process',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      size: 16,
                      color: Colors.white,
                    ),
                  ],
                ),
              );
            },
          ),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 200),
          alignment: Alignment.topCenter,
          child: _expanded
              ? Container(
                  margin: const EdgeInsets.only(top: 8),
                  width: double.infinity,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: widget.toolCalls.map((tc) {
                      return _ToolCallCard(rawText: tc);
                    }).toList(),
                  ),
                )
              : const SizedBox.shrink(),
        ),
      ],
      ),
    );
  }
}

/// Renders a single tool_call as a readable card.
class _ToolCallCard extends StatelessWidget {
  final String rawText;

  const _ToolCallCard({required this.rawText});

  @override
  Widget build(BuildContext context) {
    // Try to parse JSON tool call.
    final parsed = _parseToolCall(rawText);

    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1C1C),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: PorterTheme.surfaceBorder),
      ),
      child: parsed != null ? _buildReadable(parsed) : _buildRaw(),
    );
  }

  Widget _buildReadable(_ParsedToolCall tc) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Function name badge.
        Row(
          children: [
            Icon(
              tc.isResponse ? Icons.check_circle_outline : Icons.functions,
              size: 13,
              color: tc.isResponse
                  ? PorterTheme.successGreen
                  : PorterTheme.accentCyan,
            ),
            const SizedBox(width: 6),
            Text(
              tc.name,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: tc.isResponse
                    ? PorterTheme.successGreen
                    : PorterTheme.accentCyan,
              ),
            ),
          ],
        ),
        if (tc.params.isNotEmpty) ...[
          const SizedBox(height: 6),
          ...tc.params.entries.map((e) {
            return Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${e.key}: ',
                    style: const TextStyle(
                      fontSize: 11,
                      color: PorterTheme.textTertiary,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  Expanded(
                    child: Text(
                      '${e.value}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: PorterTheme.textSecondary,
                      ),
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ],
    );
  }

  Widget _buildRaw() {
    return Text(
      rawText,
      style: const TextStyle(
        fontSize: 11,
        fontFamily: 'monospace',
        color: PorterTheme.textTertiary,
        height: 1.4,
      ),
    );
  }

  /// Try to parse tool call JSON into structured data.
  static _ParsedToolCall? _parseToolCall(String text) {
    try {
      // Pattern 1: {"name": "func", "arguments": {...}}
      if (text.contains('"name"') && text.contains('"arguments"')) {
        final json = _extractJson(text);
        if (json != null) {
          final name = json['name'] as String? ?? 'unknown';
          final args = json['arguments'];
          final params = <String, dynamic>{};
          if (args is Map) {
            params.addAll(args.cast<String, dynamic>());
          }
          return _ParsedToolCall(
              name: name, params: params, isResponse: false);
        }
      }

      // Pattern 2: {"options": [...], ...} (response object)
      if (text.contains('"options"') || text.contains('"type"')) {
        final json = _extractJson(text);
        if (json != null) {
          return _ParsedToolCall(
            name: 'response',
            params: json.cast<String, dynamic>(),
            isResponse: true,
          );
        }
      }
    } catch (_) {}
    return null;
  }

  /// Extract the first JSON object from text.
  static Map<String, dynamic>? _extractJson(String text) {
    final start = text.indexOf('{');
    if (start < 0) return null;
    int depth = 0;
    int end = start;
    for (int i = start; i < text.length; i++) {
      if (text[i] == '{') depth++;
      if (text[i] == '}') depth--;
      if (depth == 0) {
        end = i + 1;
        break;
      }
    }
    try {
      final jsonStr = text.substring(start, end);
      final decoded = json.decode(jsonStr);
      if (decoded is Map<String, dynamic>) return decoded;
    } catch (_) {}
    return null;
  }
}

class _ParsedToolCall {
  final String name;
  final Map<String, dynamic> params;
  final bool isResponse;
  const _ParsedToolCall({
    required this.name,
    required this.params,
    required this.isResponse,
  });
}

/// Feedback row — thumbs up/down + regenerate.
class _FeedbackRow extends StatefulWidget {
  final ChatMessage message;
  final bool showRegenerate;

  const _FeedbackRow({
    required this.message,
    required this.showRegenerate,
  });

  @override
  State<_FeedbackRow> createState() => _FeedbackRowState();
}

class _FeedbackRowState extends State<_FeedbackRow> {
  int _feedback = 0; // -1 down, 0 none, 1 up

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _feedbackButton(
            icon: Icons.thumb_up_outlined,
            activeIcon: Icons.thumb_up,
            isActive: _feedback == 1,
            onTap: () => setState(() => _feedback = _feedback == 1 ? 0 : 1),
          ),
          const SizedBox(width: 4),
          _feedbackButton(
            icon: Icons.thumb_down_outlined,
            activeIcon: Icons.thumb_down,
            isActive: _feedback == -1,
            onTap: () => setState(() => _feedback = _feedback == -1 ? 0 : -1),
          ),
          if (widget.showRegenerate) ...[
            const SizedBox(width: 4),
            _feedbackButton(
              icon: Icons.refresh,
              activeIcon: Icons.refresh,
              isActive: false,
              onTap: () {
                final chat =
                    Provider.of<ChatProvider>(context, listen: false);
                chat.regenerateLastResponse();
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _feedbackButton({
    required IconData icon,
    required IconData activeIcon,
    required bool isActive,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.all(6),
        child: Icon(
          isActive ? activeIcon : icon,
          size: 15,
          color: isActive ? PorterTheme.accentCyan : PorterTheme.textTertiary,
        ),
      ),
    );
  }
}

/// Animated typing indicator — three pulsing dots.
class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 4),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: PorterTheme.surfaceCard,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: PorterTheme.surfaceBorder),
          ),
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              return Row(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(3, (i) {
                  final phase = (_controller.value + i * 0.15) % 1.0;
                  final alpha = 0.3 + 0.7 * sin(phase * pi);
                  return Container(
                    width: 7,
                    height: 7,
                    margin: EdgeInsets.only(right: i < 2 ? 4 : 0),
                    decoration: BoxDecoration(
                      color:
                          PorterTheme.accentCyan.withValues(alpha: alpha),
                      shape: BoxShape.circle,
                    ),
                  );
                }),
              );
            },
          ),
        ),
      ),
    );
  }
}

/// Blinking cursor shown during streaming before text appears.
class _StreamingCursor extends StatefulWidget {
  const _StreamingCursor();

  @override
  State<_StreamingCursor> createState() => _StreamingCursorState();
}

class _StreamingCursorState extends State<_StreamingCursor>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          return Container(
            width: 2,
            height: 16,
            decoration: BoxDecoration(
              color: PorterTheme.accentCyan
                  .withValues(alpha: _controller.value),
              borderRadius: BorderRadius.circular(1),
            ),
          );
        },
      ),
    );
  }
}

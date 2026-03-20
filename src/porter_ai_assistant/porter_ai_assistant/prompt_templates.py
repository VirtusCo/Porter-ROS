# Copyright 2026 VirtusCo
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Prompt template management for Porter AI Assistant.

Handles system prompt selection based on query context, adapter type,
and language. Loads templates from system_prompts.yaml.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Fallback prompts if YAML file is unavailable
FALLBACK_PROMPTS = {
    'default': (
        'You are Virtue, a helpful and friendly airport assistant robot '
        'made by VirtusCo. You help passengers with directions, flight '
        'information, and luggage. Keep responses concise and actionable. '
        'Offer to carry bags and escort passengers when appropriate.'
    ),
    'tool_use': (
        'You are Virtue, an airport assistant robot by VirtusCo. '
        'Call tools using <tool_call>{"name": "tool_name", '
        '"arguments": {...}}</tool_call> format. After tool results in '
        '<tool_response>...</tool_response>, respond naturally.\n\n'
        'Tools:\n'
        '- get_directions(destination, from_location?) - Walking directions\n'
        '- get_flight_status(flight_number) - Flight status, gate, delays\n'
        '- find_nearest(facility_type, accessible?) - Nearest facility\n'
        '- weigh_luggage(num_bags) - Weigh bags on built-in scale\n'
        '- get_gate_info(gate_id) - Gate terminal and concourse info\n'
        '- call_assistance(assistance_type, location, priority?) - '
        'Request staff help\n'
        '- escort_passenger(destination, carry_luggage?, pace?) - '
        'Navigate passenger\n'
        '- show_map(area, highlight?, show_route?) - Display airport map\n'
        '- check_wait_time(queue_type, terminal?) - Queue wait times\n'
        '- set_reminder(flight_number, reminder_minutes_before?) - '
        'Boarding reminder\n'
        '- get_airline_counter(airline, service_type?) - Airline counter\n'
        '- get_transport_options(destination, transport_type?) - '
        'Ground transport\n'
        '- translate_text(text, target_language) - Translate text\n'
        '- report_incident(incident_type, location, severity, '
        'description?) - Report incident'
    ),
}


class PromptManager:
    """Manage system prompt templates for the Porter AI Assistant.

    Loads prompt templates from a YAML file and provides selection logic
    based on query type, adapter, and context.

    Attributes:
        prompts: Dictionary mapping prompt keys to prompt strings.
    """

    def __init__(self, yaml_path: Optional[str] = None):
        """Initialize prompt manager.

        Args:
            yaml_path: Path to system_prompts.yaml. If None, uses fallbacks.
        """
        self.prompts: dict = {}
        if yaml_path:
            self.load(yaml_path)
        else:
            self.prompts = FALLBACK_PROMPTS.copy()

    def load(self, yaml_path: str) -> bool:
        """Load prompts from YAML file.

        Args:
            yaml_path: Path to system_prompts.yaml.

        Returns:
            True if loaded successfully.
        """
        path = Path(yaml_path)
        if not path.exists():
            logger.warning('Prompts file not found: %s, using fallbacks', path)
            self.prompts = FALLBACK_PROMPTS.copy()
            return False

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)

            self.prompts = {}
            if 'system_prompts' in data:
                for entry in data['system_prompts']:
                    key = entry.get('key', '')
                    prompt = entry.get('prompt', '')
                    if key and prompt:
                        self.prompts[key] = prompt

            logger.info('Loaded %d prompt templates', len(self.prompts))
            return True

        except Exception as e:
            logger.error('Failed to load prompts: %s', e)
            self.prompts = FALLBACK_PROMPTS.copy()
            return False

    def get(self, key: str = 'default') -> str:
        """Retrieve a prompt by key.

        Args:
            key: Prompt key (e.g., 'default', 'wayfinding', 'tool_use').

        Returns:
            Prompt string. Falls back to 'default' if key not found.
        """
        if key in self.prompts:
            return self.prompts[key]

        if 'default' in self.prompts:
            logger.debug("Prompt '%s' not found, using default", key)
            return self.prompts['default']

        return FALLBACK_PROMPTS['default']

    def get_for_adapter(self, adapter_type: str, context_key: str = '') -> str:
        """Select the best prompt for a given adapter and context.

        Args:
            adapter_type: 'conversational' or 'tool_use'.
            context_key: Optional context hint (e.g., 'wayfinding', 'emergency').

        Returns:
            Best matching prompt string.
        """
        if adapter_type == 'tool_use':
            return self.get('tool_use')

        if context_key and context_key in self.prompts:
            return self.get(context_key)

        return self.get('default')

    @property
    def available_keys(self) -> list:
        """List all available prompt keys."""
        return sorted(self.prompts.keys())

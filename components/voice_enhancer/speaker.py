import esphome.codegen as cg
from esphome.components import audio, speaker
import esphome.config_validation as cv
from esphome.const import (
    CONF_BITS_PER_SAMPLE,
    CONF_ID,
    CONF_NUM_CHANNELS,
    CONF_OUTPUT_SPEAKER,
    CONF_SAMPLE_RATE,
)
from esphome.core.entity_helpers import inherit_property_from

AUTO_LOAD = ["audio"]
DEPENDENCIES = ["speaker"]
CODEOWNERS = ["@axiomantic"]

voice_enhancer_ns = cg.esphome_ns.namespace("voice_enhancer")
VoiceEnhancerSpeaker = voice_enhancer_ns.class_(
    "VoiceEnhancerSpeaker", cg.Component, speaker.Speaker
)

CONF_HPF_ENABLED = "hpf_enabled"
CONF_PRESENCE_ENABLED = "presence_enabled"
CONF_COMPRESSOR_ENABLED = "compressor_enabled"
CONF_LIMITER_ENABLED = "limiter_enabled"


def _set_stream_limits(config):
    audio.set_stream_limits(
        min_bits_per_sample=16,
        max_bits_per_sample=32,
    )(config)
    return config


def _validate_audio_compatibility(config):
    inherit_property_from(CONF_NUM_CHANNELS, CONF_OUTPUT_SPEAKER)(config)
    inherit_property_from(CONF_SAMPLE_RATE, CONF_OUTPUT_SPEAKER)(config)
    inherit_property_from(CONF_BITS_PER_SAMPLE, CONF_OUTPUT_SPEAKER)(config)


CONFIG_SCHEMA = cv.All(
    speaker.SPEAKER_SCHEMA.extend(
        {
            cv.GenerateID(): cv.declare_id(VoiceEnhancerSpeaker),
            cv.Required(CONF_OUTPUT_SPEAKER): cv.use_id(speaker.Speaker),
            cv.Optional(CONF_HPF_ENABLED, default=True): cv.boolean,
            cv.Optional(CONF_PRESENCE_ENABLED, default=True): cv.boolean,
            cv.Optional(CONF_COMPRESSOR_ENABLED, default=True): cv.boolean,
            cv.Optional(CONF_LIMITER_ENABLED, default=True): cv.boolean,
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _set_stream_limits,
)

FINAL_VALIDATE_SCHEMA = _validate_audio_compatibility


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await speaker.register_speaker(var, config)

    output_spkr = await cg.get_variable(config[CONF_OUTPUT_SPEAKER])
    cg.add(var.set_output_speaker(output_spkr))
    cg.add(var.set_hpf_enabled(config[CONF_HPF_ENABLED]))
    cg.add(var.set_presence_enabled(config[CONF_PRESENCE_ENABLED]))
    cg.add(var.set_compressor_enabled(config[CONF_COMPRESSOR_ENABLED]))
    cg.add(var.set_limiter_enabled(config[CONF_LIMITER_ENABLED]))

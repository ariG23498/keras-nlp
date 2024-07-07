# Copyright 2023 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from functools import partial

import numpy as np

from keras_nlp.src.utils.preset_utils import HF_CONFIG_FILE
from keras_nlp.src.utils.preset_utils import SAFETENSOR_CONFIG_FILE
from keras_nlp.src.utils.preset_utils import get_file
from keras_nlp.src.utils.preset_utils import jax_memory_cleanup
from keras_nlp.src.utils.preset_utils import load_config
from keras_nlp.src.utils.transformers.safetensor_utils import set_keras_weight


def load_gemma_backbone(cls, preset, load_weights):
    """
    Load and initialize the PaliGemma backbone model.

    Args:
        cls (class): Keras model class.
        preset (str): Preset configuration name.
        load_weights (bool): Whether to load the weights.

    Returns:
        backbone: Initialized Keras model backbone.
    """
    transformers_config = load_config(preset, HF_CONFIG_FILE)
    text_config = transformers_config["text_config"]
    vision_config = transformers_config["vision_config"]
    backbone = cls(
        vocabulary_size=transformers_config["image_token_index"],
        image_size=(
            vision_config["image_size"]
            if "image_size" in vision_config.keys()
            else 224
        ),
        num_layers=text_config["num_hidden_layers"],
        num_query_heads=text_config["num_attention_heads"],
        num_key_value_heads=text_config["num_key_value_heads"],
        hidden_dim=text_config["hidden_size"],
        intermediate_dim=text_config["intermediate_size"] * 2,
        head_dim=text_config["num_image_tokens"],
        vit_patch_size=vision_config["patch_size"],
        vit_num_heads=vision_config["num_attention_heads"],
        vit_hidden_dim=vision_config["hidden_size"],
        vit_num_layers=vision_config["num_hidden_layers"],
        vit_intermediate_dim=vision_config["intermediate_size"],
    )

    if not load_weights:
        return backbone

    jax_memory_cleanup(backbone)
    # Code to port the weights from safetensors into the keras nlp model
    safetensor_config = load_config(preset, SAFETENSOR_CONFIG_FILE)
    safetensor_files = {
        fname: get_file(preset, fname)
        for fname in set(safetensor_config["weight_map"].values())
    }
    port_weight = partial(
        set_keras_weight,
        safetensor_files=safetensor_files,
        safetensor_config=safetensor_config,
    )

    ############################################################################
    # Image Tower
    ############################################################################
    image_encoder = backbone.vit_encoder.get_layer("image_encoder")

    # Embedding
    port_weight(
        keras_variable=image_encoder.vision_embeddings.patch_embedding.bias,
        hf_weight_key="vision_tower.vision_model.embeddings.patch_embedding.bias",
    )

    port_weight(
        keras_variable=image_encoder.vision_embeddings.patch_embedding.kernel,
        hf_weight_key="vision_tower.vision_model.embeddings.patch_embedding.weight",
        hook_fn=lambda hf_tensor, keras_shape: np.transpose(
            hf_tensor,
            axes=(2, 3, 1, 0),
        ),
    )

    # Positional Embedding
    port_weight(
        keras_variable=image_encoder.vision_embeddings.position_embedding.embeddings,
        hf_weight_key="vision_tower.vision_model.embeddings.position_embedding.weight",
    )

    # Normalization
    port_weight(
        keras_variable=image_encoder.encoder_layer_norm.gamma,
        hf_weight_key="vision_tower.vision_model.post_layernorm.weight",
    )

    port_weight(
        keras_variable=image_encoder.encoder_layer_norm.beta,
        hf_weight_key="vision_tower.vision_model.post_layernorm.bias",
    )

    # ResBlocks
    for index in range(image_encoder.num_layers):
        block = image_encoder.resblocks[index]

        port_weight(
            keras_variable=block.layer_norm_1.beta,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.layer_norm1.bias",
        )

        port_weight(
            keras_variable=block.layer_norm_1.gamma,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.layer_norm1.weight",
        )

        port_weight(
            keras_variable=block.layer_norm_2.beta,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.layer_norm2.bias",
        )

        port_weight(
            keras_variable=block.layer_norm_2.gamma,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.layer_norm2.weight",
        )

        port_weight(
            keras_variable=block.mlp_dense_1.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.mlp.fc1.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

        port_weight(
            keras_variable=block.mlp_dense_1.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.mlp.fc1.bias",
        )

        port_weight(
            keras_variable=block.mlp_dense_2.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.mlp.fc2.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

        port_weight(
            keras_variable=block.mlp_dense_2.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.mlp.fc2.bias",
        )

        port_weight(
            keras_variable=block.attn.key_proj.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.k_proj.bias",
        )

        port_weight(
            keras_variable=block.attn.key_proj.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.k_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

        port_weight(
            keras_variable=block.attn.out_proj.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.out_proj.bias",
        )

        port_weight(
            keras_variable=block.attn.out_proj.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.out_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

        port_weight(
            keras_variable=block.attn.query_proj.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.q_proj.bias",
        )

        port_weight(
            keras_variable=block.attn.query_proj.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.q_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

        port_weight(
            keras_variable=block.attn.value_proj.bias,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.v_proj.bias",
        )

        port_weight(
            keras_variable=block.attn.value_proj.kernel,
            hf_weight_key=f"vision_tower.vision_model.encoder.layers.{index}.self_attn.v_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                hf_tensor,
                axes=(1, 0),
            ),
        )

    # Multi Modal Projection
    port_weight(
        keras_variable=backbone.vit_encoder.get_layer(
            "image_classifier"
        ).kernel,
        hf_weight_key="multi_modal_projector.linear.weight",
        hook_fn=lambda hf_tensor, keras_shape: np.transpose(
            hf_tensor,
            axes=(1, 0),
        ),
    )

    port_weight(
        keras_variable=backbone.vit_encoder.get_layer("image_classifier").bias,
        hf_weight_key="multi_modal_projector.linear.bias",
    )

    ############################################################################
    # Language Tower
    ############################################################################
    for index in range(backbone.num_layers):
        decoder_layer = backbone.transformer_layers[index]

        # Norm layers
        port_weight(
            keras_variable=decoder_layer.pre_attention_norm.scale,
            hf_weight_key=f"language_model.model.layers.{index}.input_layernorm.weight",
        )
        port_weight(
            keras_variable=decoder_layer.pre_ffw_norm.scale,
            hf_weight_key=f"language_model.model.layers.{index}.post_attention_layernorm.weight",
        )

        # Attention layers
        port_weight(
            keras_variable=decoder_layer.attention.query_dense.kernel,
            hf_weight_key=f"language_model.model.layers.{index}.self_attn.q_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                np.reshape(
                    hf_tensor,
                    (keras_shape[0], keras_shape[2], keras_shape[1]),
                ),
                axes=(0, 2, 1),
            ),
        )
        port_weight(
            keras_variable=decoder_layer.attention.key_dense.kernel,
            hf_weight_key=f"language_model.model.layers.{index}.self_attn.k_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                np.reshape(
                    hf_tensor,
                    (keras_shape[0], keras_shape[2], keras_shape[1]),
                ),
                axes=(0, 2, 1),
            ),
        )
        port_weight(
            keras_variable=decoder_layer.attention.value_dense.kernel,
            hf_weight_key=f"language_model.model.layers.{index}.self_attn.v_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                np.reshape(
                    hf_tensor,
                    (keras_shape[0], keras_shape[2], keras_shape[1]),
                ),
                axes=(0, 2, 1),
            ),
        )
        port_weight(
            keras_variable=decoder_layer.attention.output_dense.kernel,
            hf_weight_key=f"language_model.model.layers.{index}.self_attn.o_proj.weight",
            hook_fn=lambda hf_tensor, keras_shape: np.transpose(
                np.reshape(
                    hf_tensor,
                    (keras_shape[2], keras_shape[0], keras_shape[1]),
                ),
                axes=(1, 2, 0),
            ),
        )

        # MLP layers
        port_weight(
            keras_variable=decoder_layer.gating_ffw.variables[0],
            hf_weight_key=f"language_model.model.layers.{index}.mlp.gate_proj.weight",
            hook_fn=lambda hf_tensor, _: np.transpose(hf_tensor, axes=(1, 0)),
        )
        port_weight(
            keras_variable=decoder_layer.gating_ffw_2.variables[0],
            hf_weight_key=f"language_model.model.layers.{index}.mlp.up_proj.weight",
            hook_fn=lambda hf_tensor, _: np.transpose(hf_tensor, axes=(1, 0)),
        )
        port_weight(
            keras_variable=decoder_layer.ffw_linear.variables[0],
            hf_weight_key=f"language_model.model.layers.{index}.mlp.down_proj.weight",
            hook_fn=lambda hf_tensor, _: np.transpose(hf_tensor, axes=(1, 0)),
        )

    # Normalization
    port_weight(
        keras_variable=backbone.layer_norm.scale,
        hf_weight_key="language_model.model.norm.weight",
    )

    # Embedding
    port_weight(
        keras_variable=backbone.token_embedding.embeddings,
        hf_weight_key="language_model.model.embed_tokens.weight",
        hook_fn=lambda hf_tensor, keras_shape: hf_tensor[: keras_shape[0]],
    )

    return backbone


def load_gemma_tokenizer(cls, preset):
    """
    Load the Gemma tokenizer.

    Args:
        cls (class): Tokenizer class.
        preset (str): Preset configuration name.

    Returns:
        tokenizer: Initialized tokenizer.
    """
    return cls(get_file(preset, "tokenizer.model"))

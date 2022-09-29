"""
Title: Random Walks with Stable Diffusion in KerasCV
Authors: Ian Stenbit, [fchollet](https://twitter.com/fchollet), [lukewood](https://twitter.com/luke_wood_ml)
Date created: 2022/09/28
Last modified: 2022/09/28
Description: Explore the latent manifold of Stable Diffusion
"""

"""
## Overview

Generative models learn a low dimensional latent representation of their
training data.  The inference process for these models typically involves
starting from some point in latent space and running the latent vector
through the decoder portion of the generative model.  StableDiffusion
has two latent spaces: the image representation space learned by the
Variation AutoEncoder used during training, and the prompt latent space
which is learned using a combination of pretraining and train time
finetuning.

Latent walking, or latent exploration is the process of
sampling a point in latent space and incrementally changing the latent
representation.  Its most common application is generating videos or gifs,
where each sampled point is fed to the decoder and is stored as a
frame in the final gif or video.
For high quality latent representations, this produces coherent looking
videos.  These videos can provide insight into the feature map of the
latent space, and can ultimately lead to improvements in the training
process.  One such GIF is displayed below:

![Panda to Plane](https://imgur.com/a/hlmii8V)

In this guide, we will show how to take advantage of the Stable Diffusion API
in KerasCV to perform prompt interpolation and circular walks through
 StableDiffusion's learned latent space for image representation, as well as through
 the text encoder's latent manifold.

 This guide assumes the reader has a
high-level understanding of Stable Diffusion.
If you haven't already, you should start
by reading the [Stable Diffusion Tutorial](https://keras.io/guides/keras_cv/generate_images_with_stable_diffusion/).

To start, we import KerasCV and load up a stable diffusion model using the
optimizations discussed in the Stable Diffusion tutorial.
Note that if you are running with a M1 Mac GPU you should not enabled mixed precision.
Check out the [basic Stable Diffusion tutorial](https://keras.io/guides/keras_cv/generate_images_with_stable_diffusion/) for more info.
"""

"""shell
pip install --upgrade keras-cv
"""

import keras_cv
from tensorflow import keras
import matplotlib.pyplot as plt
import tensorflow as tf
import math
from PIL import Image


keras.mixed_precision.set_global_policy("mixed_float16")
model = keras_cv.models.StableDiffusion(jit_compile=True)

"""
## Interpolating Between Text Prompts

In stable diffusion, a text prompt is encoded, and that encoding is used to
guide the diffusion process. The latent manifold of this encoding has shape
77x768 (that's huge!), and when we give StableDiffusion a text prompt, we're
generating images from just one point in this manifold.

To explore more of this manifold, we can interpolate between two text encodings
and generate images at those interpolated points:
"""

prompt_1 = "A watercolor painting of a Golden Retriever at the beach"
prompt_2 = "A still life DSLR photo of a bowl of fruit"
interpolation_steps = 5

encoding_1 = tf.squeeze(model.encode_text(prompt_1))
encoding_2 = tf.squeeze(model.encode_text(prompt_2))

interpolated_encodings = tf.linspace(encoding_1, encoding_2, interpolation_steps)

# Show the size of the latent manifold
print(encoding_1.shape)

"""
Once we've interpolated the encodings, we can generate images from each point.
Note that in order to maintain some stability between the resulting images we
keep the diffusion noise constant between images.
"""

seed = 12345
noise = tf.random.normal((512 // 8, 512 // 8, 4), seed=seed)

images = model.generate_image(
    interpolated_encodings,
    batch_size=interpolation_steps,
    diffusion_noise=noise,
)

"""
Now that we've generated some interpolated images, let's take a look at them!

Throughout this tutorial, we're going to export sequences of images as gifs so
that they can be easily viewed with some temporal context. For sequences of
images where the first and last images don't match conceptually, we rubber-band
the gif.
"""

def export_as_gif(filename, images, frames_per_second=10, rubber_band=False):
    if rubber_band:
        images += images[2:-1][::-1]
    images[0].save(filename, save_all=True, append_images=images[1:],
                   duration=1000 // frames_per_second, loop=0)

export_as_gif("doggo-and-fruit-5.gif", [Image.fromarray(img) for img in images],
              frames_per_second=2, rubber_band=True)

"""
![Dog to Fruit 5](https://imgur.com/a/LHXceUi)

The results may seem surprising. Generally, interpolating between prompts
produces coherent looking images, and often demonstrate a progressive concept
shift between the contents of the two prompts. This is indiciative of a high
quality representation space.

To best visualize this, we should do a much more fine-grained interpolation,
using hundreds of steps. In order to keep batch size small (so that we don't
OOM our accelerators), this requires manually batching our interpolated
encodings.
"""

interpolation_steps = 160
batch_size = 16

encoding_step = (encoding_2 - encoding_1) / interpolation_steps
encoding_step = tf.squeeze(encoding_step)

images = []
for step_index in range(interpolation_steps // batch_size):
    step_offsets = tf.linspace(batch_size*step_index,
                               batch_size*(step_index+1) - 1, batch_size)
    step_offsets = tf.tensordot(tf.cast(step_offsets, encoding_step.dtype),
                                encoding_step, 0)
    encodings = encoding_1 + tf.cast(step_offsets, encoding_1.dtype)
    images += [Image.fromarray(img) for img in model.generate_image(
        encodings,
        batch_size=batch_size,
        num_steps=25,
        diffusion_noise=noise,
    )]

export_as_gif("doggo-and-fruit-160.gif", images, rubber_band=True)

"""
![Dog to Fruit 160](https://imgur.com/a/8B1kHoN)

The resulting gif shows a much clearer and more coherent shift between the two
prompts. Try out some prompts of your own and experiment!

## A Random Walk Around a Text Prompt

Our next experiment will be to go for a random walk around the latent manifold
starting from a point produced by a particular prompt.
"""

walk_steps = 160
batch_size = 16
step_size = .05

encoding = model.encode_text("A rubber duck swimming in a bowl of cereal")

images = []
for step_index in range(walk_steps // batch_size):
    batch_encodings = []
    for individual_image_step in range(batch_size):
        batch_encodings.append(encoding)
        # Note that (77, 768) is the shape of the text encoding.
        random_deltas = tf.random.normal((77, 768), stddev=step_size, seed=seed)
        encoding += random_deltas
    batch_encodings = tf.stack(batch_encodings)
    images += [Image.fromarray(img) for img in model.generate_image(
        batch_encodings,
        batch_size=batch_size,
        num_steps=25,
        diffusion_noise=noise,
    )]

export_as_gif("ducky.gif", images, rubber_band=True)

"""
![Rubber Ducky Goes on a Walk](https://imgur.com/a/KZG8vyg)

Perhaps unsurprisingly, randomly walking through the encoder's latent manifold
produces a lot of images that look incoherent. Try it for yourself by setting
your own prompt, and adjusting step_size to increase or decrease the magnitude
of the walk. Note that when the magnitude of the walk gets large, the walk often
leads into spaces in the latent manifold which produce extremely noisy images.

## A Random Walk Through the Diffusion Noise Space for a Single Prompt

Our final experiment is to stick to one prompt and explore the variety of images
that the diffusion model can produce from that prompt. We do this by controlling
the noise that is used to seed the diffusion process.

We create two noise components, x, and y, and do a walk from 0 to 2PI, summing
the cosine of our x component and the sin of our y component to produce noise.
Using this approach, the end of our walk arrives at the same noise inputs where
we began our walk, so we get a "loopable" result!
"""

prompt = "An oil paintings of cows in a field next to a windmill in Holland"
encoding = model.encode_text(prompt)
walk_steps = 160
batch_size = 16

walk_noise_x = tf.random.normal(noise.shape, dtype=tf.float64)
walk_noise_y = tf.random.normal(noise.shape, dtype=tf.float64)

images = []
for step in range(walk_steps // batch_size):
    walk_scale_x = tf.cos(tf.linspace(batch_size*step, batch_size*(step+1) - 1, batch_size) * 2 * math.pi / walk_steps)
    walk_scale_y = tf.sin(tf.linspace(batch_size*step, batch_size*(step+1) - 1, batch_size) * 2 * math.pi / walk_steps)
    noise_x = tf.tensordot(walk_scale_x, walk_noise_x, axes=0)
    noise_y = tf.tensordot(walk_scale_y, walk_noise_y, axes=0)
    noise = tf.add(noise_x, noise_y)
    images += [Image.fromarray(img) for img in model.generate_image(
        encoding,
        batch_size=batch_size,
        num_steps=25,
        diffusion_noise=noise,
    )]

export_as_gif("cows.gif", images)

"""
![Happy Cows](https://imgur.com/a/5tPC4Zl)

Experiment with your own prompts and with different values of
`unconditional_guidance_scale`!

## Conclusion

Stable Diffusion offers a lot more than just single text-to-image translations.
Exploring the latent manifold of the text encoder and the noise space of the
diffusion model are two fun ways to experience the power of this model, and
KerasCV makes it easy to explore!
"""

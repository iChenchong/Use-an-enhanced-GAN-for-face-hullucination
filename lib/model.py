from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf
from lib.ops import *
import collections
import os
import math
import scipy.misc as sic
import numpy as np


# Define the dataloader 
def data_loader(FLAGS):
    with tf.device('/cpu:0'):
        # Define the returned data batches 
        Data = collections.namedtuple('Data', 'paths_LR, paths_HR, path_Edge, inputs, targets, assists, image_count, steps_per_epoch')

        #Check the input directory 
        if (FLAGS.input_dir_LR == 'None') or (FLAGS.input_dir_HR == 'None'):
            raise ValueError('Input directory is not provided')

        if (not os.path.exists(FLAGS.input_dir_LR)) or (not os.path.exists(FLAGS.input_dir_HR)):
            raise ValueError('Input directory not found')

        image_list_LR = os.listdir(FLAGS.input_dir_LR)
        image_list_LR = [_ for _ in image_list_LR if _.endswith('.png')]
        if len(image_list_LR)==0:
            raise Exception('No png files in the input directory')

        image_list_LR_temp = sorted(image_list_LR)
        image_list_LR = [os.path.join(FLAGS.input_dir_LR, _) for _ in image_list_LR_temp]
        image_list_HR = [os.path.join(FLAGS.input_dir_HR, _) for _ in image_list_LR_temp]
		image_list_Edge = [os.path.join(FLAGS.input_dir_Edge, _) for _ in image_list_LR_temp]

        image_list_LR_tensor = tf.convert_to_tensor(image_list_LR, dtype=tf.string)
        image_list_HR_tensor = tf.convert_to_tensor(image_list_HR, dtype=tf.string)
		image_list_Edge_tensor = tf.convert_to_tensor(image_list_Edge, dtype=tf.string)

        with tf.variable_scope('load_image'):
            # define the image list queue
            # image_list_LR_queue = tf.train.string_input_producer(image_list_LR, shuffle=False, capacity=FLAGS.name_queue_capacity)
            # image_list_HR_queue = tf.train.string_input_producer(image_list_HR, shuffle=False, capacity=FLAGS.name_queue_capacity)
            #print('[Queue] image list queue use shuffle: %s'%(FLAGS.mode == 'Train'))
            output = tf.train.slice_input_producer([image_list_LR_tensor, image_list_HR_tensor, image_list_Edge_tensor],
                                                   shuffle=False, capacity=FLAGS.name_queue_capacity)

            # Reading and decode the images
            reader = tf.WholeFileReader(name='image_reader')
            image_LR = tf.read_file(output[0])
            image_HR = tf.read_file(output[1])
			image_Edge = tf.read_file(output[2])
            input_image_LR = tf.image.decode_png(image_LR, channels=3)
            input_image_HR = tf.image.decode_png(image_HR, channels=3)
			input_image_Edge = tf.image.decode_png(image_Edge, channels=1)
            input_image_LR = tf.image.convert_image_dtype(input_image_LR, dtype=tf.float32)
            input_image_HR = tf.image.convert_image_dtype(input_image_HR, dtype=tf.float32)
			input_image_Edge = tf.image.convert_image_dtype(input_image_Edge, dtype=tf.float32)

            assertion = tf.assert_equal(tf.shape(input_image_LR)[2], 3, message="image does not have 3 channels")
            with tf.control_dependencies([assertion]):
                input_image_LR = tf.identity(input_image_LR)
                input_image_HR = tf.identity(input_image_HR)
				input_image_Edge = tf.identity(input_image_Edge)

            # Normalize the low resolution image to [0, 1], high resolution to [-1, 1]
            a_image = preprocessLR(input_image_LR)
            b_image = preprocess(input_image_HR)
			c_image = preprocess(input_image_Edge)

            inputs, targets = [a_image, b_image, c_image]

        # The data augmentation part
        with tf.name_scope('data_preprocessing'):
            with tf.name_scope('random_crop'):
                # Check whether perform crop
                if (FLAGS.random_crop is True) and FLAGS.mode == 'train':
                    print('[Config] Use random crop')
                    # Set the shape of the input image. the target will have 4X size
                    input_size = tf.shape(inputs)
                    target_size = tf.shape(targets)
                    offset_w = tf.cast(tf.floor(tf.random_uniform([], 0, tf.cast(input_size[1], tf.float32) - FLAGS.crop_size)),
                                       dtype=tf.int32)
                    offset_h = tf.cast(tf.floor(tf.random_uniform([], 0, tf.cast(input_size[0], tf.float32) - FLAGS.crop_size)),
                                       dtype=tf.int32)
		    print (offset_w)
                    if FLAGS.task == 'SRGAN' or FLAGS.task == 'SRResnet':
                        inputs = tf.image.crop_to_bounding_box(inputs, offset_h, offset_w, FLAGS.crop_size,
                                                               FLAGS.crop_size)
                        targets = tf.image.crop_to_bounding_box(targets, offset_h*4, offset_w*4, FLAGS.crop_size*4,
                                                                FLAGS.crop_size*4)
                    elif FLAGS.task == 'denoise':
                        inputs = tf.image.crop_to_bounding_box(inputs, offset_h, offset_w, FLAGS.crop_size,
                                                               FLAGS.crop_size)
                        targets = tf.image.crop_to_bounding_box(targets, offset_h, offset_w,
                                                                FLAGS.crop_size, FLAGS.crop_size)
                # Do not perform crop
                else:
                    inputs = tf.identity(inputs)
                    targets = tf.identity(targets)

            with tf.variable_scope('random_flip'):
                # Check for random flip:
                if (FLAGS.flip is True) and (FLAGS.mode == 'train'):
                    print('[Config] Use random flip')
                    # Produce the decision of random flip
                    decision = tf.random_uniform([], 0, 1, dtype=tf.float32)

                    input_images = random_flip(inputs, decision)
                    target_images = random_flip(targets, decision)
                else:
                    input_images = tf.identity(inputs)
                    target_images = tf.identity(targets)

            if FLAGS.task == 'SRGAN' or FLAGS.task == 'SRResnet':
                input_images.set_shape([FLAGS.crop_size, FLAGS.crop_size, 3])
                target_images.set_shape([FLAGS.crop_size*4, FLAGS.crop_size*4, 3])
            elif FLAGS.task == 'denoise':
                input_images.set_shape([FLAGS.crop_size, FLAGS.crop_size, 3])
                target_images.set_shape([FLAGS.crop_size, FLAGS.crop_size, 3])

        if FLAGS.mode == 'train':
            paths_LR_batch, paths_HR_batch, paths_Edge_batch, inputs_batch, targets_batch, assists_batch = tf.train.shuffle_batch([output[0], output[1], output[2], input_images, target_images, assists_images],
                                            batch_size=FLAGS.batch_size, capacity=FLAGS.image_queue_capacity+4*FLAGS.batch_size,
                                            min_after_dequeue=FLAGS.image_queue_capacity, num_threads=FLAGS.queue_thread)
        else:
            paths_LR_batch, paths_HR_batch, paths_Edge_batch, inputs_batch, targets_batch, assists_batch = tf.train.batch([output[0], output[1],output[2], input_images, target_images, assists_images],
                                            batch_size=FLAGS.batch_size, num_threads=FLAGS.queue_thread, allow_smaller_final_batch=True)

        steps_per_epoch = int(math.ceil(len(image_list_LR) / FLAGS.batch_size))
        if FLAGS.task == 'SRGAN' or FLAGS.task == 'SRResnet':
            inputs_batch.set_shape([FLAGS.batch_size, FLAGS.crop_size, FLAGS.crop_size, 3])
            targets_batch.set_shape([FLAGS.batch_size, FLAGS.crop_size*4, FLAGS.crop_size*4, 3])
        elif FLAGS.task == 'denoise':
            inputs_batch.set_shape([FLAGS.batch_size, FLAGS.crop_size, FLAGS.crop_size, 3])
            targets_batch.set_shape([FLAGS.batch_size, FLAGS.crop_size, FLAGS.crop_size, 3])
    return Data(
        paths_LR=paths_LR_batch,
        paths_HR=paths_HR_batch,
		paths_Edge=paths_Edge_batch��
        inputs=inputs_batch,
        targets=targets_batch,
		assists=assists_batch,
        image_count=len(image_list_LR),
        steps_per_epoch=steps_per_epoch
    )


# The test data loader. Allow input image with different size
def test_data_loader(FLAGS):
    # Get the image name list
    if (FLAGS.input_dir_LR == 'None') or (FLAGS.input_dir_HR == 'None'):
        raise ValueError('Input directory is not provided')

    if (not os.path.exists(FLAGS.input_dir_LR)) or (not os.path.exists(FLAGS.input_dir_HR)):
        raise ValueError('Input directory not found')

    image_list_LR_temp = os.listdir(FLAGS.input_dir_LR)
    image_list_LR = [os.path.join(FLAGS.input_dir_LR, _) for _ in image_list_LR_temp if _.split('.')[-1] == 'png']
    image_list_HR = [os.path.join(FLAGS.input_dir_HR, _) for _ in image_list_LR_temp if _.split('.')[-1] == 'png']

    # Read in and preprocess the images
    def preprocess_test(name, mode):
        im = sic.imread(name).astype(np.float32)
        # check grayscale image
        if im.shape[-1] != 3:
            h, w = im.shape
            temp = np.empty((h, w, 3), dtype=np.uint8)
            temp[:, :, :] = im[:, :, np.newaxis]
            im = temp.copy()
        if mode == 'LR':
            im = im / np.max(im)
        elif mode == 'HR':
            im = im / np.max(im)
            im = im * 2 - 1

        return im

    image_LR = [preprocess_test(_, 'LR') for _ in image_list_LR]
    image_HR = [preprocess_test(_, 'HR') for _ in image_list_HR]

    # Push path and image into a list
    Data = collections.namedtuple('Data', 'paths_LR, paths_HR, inputs, targets')

    return Data(
        paths_LR = image_list_LR,
        paths_HR = image_list_HR,
        inputs = image_LR,
        targets = image_HR
    )


# The inference data loader. Allow input image with different size
def inference_data_loader(FLAGS):
    # Get the image name list
    if (FLAGS.input_dir_LR == 'None'):
        raise ValueError('Input directory is not provided')

    if not os.path.exists(FLAGS.input_dir_LR):
        raise ValueError('Input directory not found')

    image_list_LR_temp = os.listdir(FLAGS.input_dir_LR)
    image_list_LR = [os.path.join(FLAGS.input_dir_LR, _) for _ in image_list_LR_temp if _.split('.')[-1] == 'png']

    # Read in and preprocess the images
    def preprocess_test(name):
        im = sic.imread(name).astype(np.float32)
        # check grayscale image
        if im.shape[-1] != 3:
            h, w = im.shape
            temp = np.empty((h, w, 3), dtype=np.uint8)
            temp[:, :, :] = im[:, :, np.newaxis]
            im = temp.copy()
        im = im / np.max(im)

        return im

    image_LR = [preprocess_test(_) for _ in image_list_LR]

    # Push path and image into a list
    Data = collections.namedtuple('Data', 'paths_LR, inputs')

    return Data(
        paths_LR=image_list_LR,
        inputs=image_LR
    )


# Definition of the generator
def generator(gen_inputs, gen_output_channels, reuse=False, FLAGS=None):
    # Check the flag
    if FLAGS is None:
        raise  ValueError('No FLAGS is provided for generator')

    # The Bx residual blocks
    def block(inputs, scope):
        with tf.variable_scope(scope):
            cat = inputs
            for j in range(6):
                with tf.variable_scope('conv_%d'%(j)):
                    net = conv2(cat, 3, 64, 1, use_bias=False, scope='conv')
                    #net = batchnorm(net, FLAGS.is_training)
                    net = prelu_tf(net)
                    cat = tf.concat([cat, net], 3)

            net = conv2(cat, 1, 128, 1, use_bias=False, scope='conv')
            net += inputs
        return net

    with tf.variable_scope('generator_unit', reuse=reuse):
        # The input layer
        with tf.variable_scope('input_stage1'):
            net = conv2(gen_inputs, 3, 128, 1, scope='conv')
            net = prelu_tf(net)

        res = net

        with tf.variable_scope('input_stage2'):
            net = conv2(gen_inputs, 3, 128, 1, scope='conv')
            #net = batchnorm(net, FLAGS.is_training)
            net = prelu_tf(net)

        # The residual block parts
        for i in range(1, FLAGS.num_block+1 , 1):
            name_scope = 'block_%d'%(i)
            net = block(net, name_scope)
            if i == 1:
                block_cat = net
            else:
                block_cat = tf.concat([block_cat, net], 3)

        with tf.variable_scope('block_scaling'):
            net = conv2(block_cat, 1, 128, 1, use_bias=False, scope='conv')

        with tf.variable_scope('residual_learning'):
            net = conv2(net, 3, 128, 1, use_bias=False, scope='conv')
            #net = batchnorm(net, FLAGS.is_training)

        net += res

        with tf.variable_scope('subpixelconv_stage1'):
            net = conv2(net, 3, 256, 1, scope='conv')
            net = pixelShuffler(net, scale=2)
            net = prelu_tf(net)

        with tf.variable_scope('subpixelconv_stage2'):
            net = conv2(net, 3, 256, 1, scope='conv')
            net = pixelShuffler(net, scale=2)
            net = prelu_tf(net)

        with tf.variable_scope('output_stage'):	    
			net = concat(2,[ net, assists])
            net = conv2(net, 3, gen_output_channels, 1, scope='conv')


    return net

# Definition of the discriminator
def discriminator(dis_inputs, FLAGS=None):
    if FLAGS is None:
        raise ValueError('No FLAGS is provided for generator')

    # Define the discriminator block
    def discriminator_block(inputs, output_channel, kernel_size, stride, scope):
        with tf.variable_scope(scope):
            net = conv2(inputs, kernel_size, output_channel, stride, use_bias=False, scope='conv1')
            net = batchnorm(net, FLAGS.is_training)
            net = lrelu(net, 0.2)

        return net

    with tf.device('/gpu:0'):
        with tf.variable_scope('discriminator_unit'):
            # The discriminator block part
            # step 1
            net = discriminator_block(dis_inputs, 64, 3, 1, 'disblock_1_1')
            
            net = discriminator_block(net, 64, 3, 2, 'disblock_1_2')
            feature1 = net

            # step 2
            d_cat2 = net
            net = discriminator_block(d_cat2, 64, 3, 1, 'disblock_2_1')
            d_cat2 = tf.concat([d_cat2, net], 3)

            net = discriminator_block(d_cat2, 128, 3, 2, 'disblock_2_2')
            feature2 = net

            # step 3
            d_cat3 = net
            for i in range(2):
                net = discriminator_block(d_cat3, 64, 3, 1, 'disblock_3_%d'%(i))
                d_cat3 = tf.concat([d_cat3, net], 3)
            
            net = discriminator_block(d_cat3, 256, 3, 2, 'disblock_3_4')
            feature3 = net
            
            # step 4
            d_cat4 = net
            for i in range(4):
                net = discriminator_block(d_cat4, 64, 3, 1, 'disblock_4_%d'%(i))
                d_cat4 = tf.concat([d_cat4, net], 3)
            
            net = discriminator_block(d_cat4, 512, 3, 2, 'disblock_4_8')
            feature4 = net
            
            # step 5
            d_cat5 = net
            for i in range(8):
                net = discriminator_block(d_cat5, 64, 3, 1, 'disblock_5_%d'%(i))
                d_cat5 = tf.concat([d_cat5, net], 3)
            
            net = discriminator_block(d_cat5, 1024, 3, 2, 'disblock_5_16')
            feature5 = net

            # The dense layer 1
            with tf.variable_scope('dense_layer_1'):
                net = slim.flatten(net)
                net = denselayer(net, 1024)
                net = lrelu(net, 0.2)

            # The dense layer 2
            with tf.variable_scope('dense_layer_2'):
                net = denselayer(net, 1)
                net = tf.nn.sigmoid(net)

    return net, feature1, feature2, feature3, feature4, feature5

# Define the whole network architecture
def SRGAN(inputs, targets, FLAGS):
    # Define the container of the parameter
    Network = collections.namedtuple('Network', 'discrim_real_output, discrim_fake_output, discrim_loss, \
        discrim_grads_and_vars, adversarial_loss, content_loss, gen_grads_and_vars, gen_output, train, global_step, \
        learning_rate')

    # Build the generator part
    with tf.variable_scope('generator'):
        output_channel = targets.get_shape().as_list()[-1]
        gen_output = generator(inputs, output_channel, reuse=False, FLAGS=FLAGS)
        gen_output.set_shape([FLAGS.batch_size, FLAGS.crop_size*4, FLAGS.crop_size*4, 3])

    # Build the fake discriminator
    with tf.name_scope('fake_discriminator'):
        with tf.variable_scope('discriminator', reuse=False):
            discrim_fake_output, fake_feature1, fake_feature2, fake_feature3, fake_feature4, fake_feature5 = discriminator(gen_output, FLAGS=FLAGS)

    # Build the real discriminator
    with tf.name_scope('real_discriminator'):
        with tf.variable_scope('discriminator', reuse=True):
            discrim_real_output, real_feature1, real_feature2, real_feature3, real_feature4, real_feature5 = discriminator(targets, FLAGS=FLAGS)

    # Use MSE loss directly
    if FLAGS.perceptual_mode == 'MSE':
        extracted_feature_gen = gen_output
        extracted_feature_target = targets

    else:
        raise NotImplementedError('Unknown perceptual type!!')

    # Calculating the generator loss
    with tf.variable_scope('generator_loss'):
        # Content loss
        with tf.variable_scope('content_loss'):
            if FLAGS.perceptual_mode == 'MSE':
                feature1_diff = fake_feature1 - real_feature1
                feature2_diff = fake_feature2 - real_feature2
                feature3_diff = fake_feature3 - real_feature3
                feature4_diff = fake_feature4 - real_feature4
                feature5_diff = fake_feature5 - real_feature5
                perceptual_loss1 = tf.reduce_mean(tf.reduce_sum(tf.abs(feature1_diff), axis=[3]))
                perceptual_loss2 = tf.reduce_mean(tf.reduce_sum(tf.abs(feature2_diff), axis=[3]))
                perceptual_loss3 = tf.reduce_mean(tf.reduce_sum(tf.abs(feature3_diff), axis=[3]))
                perceptual_loss4 = tf.reduce_mean(tf.reduce_sum(tf.abs(feature4_diff), axis=[3]))
                perceptual_loss5 = tf.reduce_mean(tf.reduce_sum(tf.abs(feature5_diff), axis=[3]))
                perceptual_loss = perceptual_loss1 + perceptual_loss2 + perceptual_loss3 + perceptual_loss4 + perceptual_loss5
                
                # Compute the euclidean distance between the two features
                diff = extracted_feature_gen - extracted_feature_target
                content_loss = tf.reduce_mean(tf.reduce_sum(tf.abs(diff), axis=[3])) + (FLAGS.p_ratio)*perceptual_loss

        with tf.variable_scope('adversarial_loss'):
            adversarial_loss = tf.reduce_mean(-tf.log(discrim_fake_output + FLAGS.EPS))
            
        gen_loss = content_loss + (FLAGS.ratio)*adversarial_loss
        print(adversarial_loss.get_shape())
        print(content_loss.get_shape())

    # Calculating the discriminator loss
    with tf.variable_scope('discriminator_loss'):
        discrim_fake_loss = tf.log(1 - discrim_fake_output + FLAGS.EPS)
        discrim_real_loss = tf.log(discrim_real_output + FLAGS.EPS)

        discrim_loss = tf.reduce_mean(-(discrim_fake_loss + discrim_real_loss)) + 0.01*perceptual_loss

    # Define the learning rate and global step
    with tf.variable_scope('get_learning_rate_and_global_step'):
        global_step = tf.contrib.framework.get_or_create_global_step()
        learning_rate = tf.train.exponential_decay(FLAGS.learning_rate, global_step, FLAGS.decay_step, FLAGS.decay_rate, staircase=FLAGS.stair)
        incr_global_step = tf.assign(global_step, global_step + 1)

    with tf.variable_scope('dicriminator_train'):
        discrim_tvars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='discriminator')
        discrim_optimizer = tf.train.AdamOptimizer(learning_rate, beta1=FLAGS.beta)
        discrim_grads_and_vars = discrim_optimizer.compute_gradients(discrim_loss, discrim_tvars)
        discrim_train = discrim_optimizer.apply_gradients(discrim_grads_and_vars)

    with tf.variable_scope('generator_train'):
        # Need to wait discriminator to perform train step
        with tf.control_dependencies([discrim_train]+ tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            gen_tvars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='generator')
            gen_optimizer = tf.train.AdamOptimizer(learning_rate, beta1=FLAGS.beta)
            gen_grads_and_vars = gen_optimizer.compute_gradients(gen_loss, gen_tvars)
            gen_train = gen_optimizer.apply_gradients(gen_grads_and_vars)

    #[ToDo] If we do not use moving average on loss??
    exp_averager = tf.train.ExponentialMovingAverage(decay=0.99)
    update_loss = exp_averager.apply([discrim_loss, adversarial_loss, content_loss])

    return Network(
        discrim_real_output = discrim_real_output,
        discrim_fake_output = discrim_fake_output,
        discrim_loss = exp_averager.average(discrim_loss),
        discrim_grads_and_vars = discrim_grads_and_vars,
        adversarial_loss = exp_averager.average(adversarial_loss),
        content_loss = exp_averager.average(content_loss),
        gen_grads_and_vars = gen_grads_and_vars,
        gen_output = gen_output,
        train = tf.group(update_loss, incr_global_step, gen_train),
        global_step = global_step,
        learning_rate = learning_rate
    )


def SRResnet(inputs, targets, FLAGS):
    # Define the container of the parameter
    Network = collections.namedtuple('Network', 'content_loss, gen_grads_and_vars, gen_output, train, global_step, \
            learning_rate')

    # Build the generator part
    with tf.variable_scope('generator'):
        output_channel = targets.get_shape().as_list()[-1]
        gen_output = generator(inputs, output_channel, reuse=False, FLAGS=FLAGS)
        gen_output.set_shape([FLAGS.batch_size, FLAGS.crop_size * 4, FLAGS.crop_size * 4, 3])

    if FLAGS.perceptual_mode == 'MSE':
        extracted_feature_gen = gen_output
        extracted_feature_target = targets

    else:
        raise NotImplementedError('Unknown perceptual type!!')

    # Calculating the generator loss
    with tf.variable_scope('generator_loss'):
        # Content loss
        with tf.variable_scope('content_loss'):
            # Compute the euclidean distance between the two features
            diff = extracted_feature_gen - extracted_feature_target
            if FLAGS.perceptual_mode == 'MSE':
                content_loss = tf.reduce_mean(tf.reduce_sum(tf.abs(diff), axis=[3]))

        gen_loss = content_loss

    # Define the learning rate and global step
    with tf.variable_scope('get_learning_rate_and_global_step'):
        global_step = tf.contrib.framework.get_or_create_global_step()
        learning_rate = tf.train.exponential_decay(FLAGS.learning_rate, global_step, FLAGS.decay_step, FLAGS.decay_rate,
                                                   staircase=FLAGS.stair)
        incr_global_step = tf.assign(global_step, global_step + 1)

    with tf.variable_scope('generator_train'):
        # Need to wait discriminator to perform train step
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            gen_tvars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, scope='generator')
            gen_optimizer = tf.train.AdamOptimizer(learning_rate, beta1=FLAGS.beta)
            gen_grads_and_vars = gen_optimizer.compute_gradients(gen_loss, gen_tvars)
            gen_train = gen_optimizer.apply_gradients(gen_grads_and_vars)

    # [ToDo] If we do not use moving average on loss??
    exp_averager = tf.train.ExponentialMovingAverage(decay=0.99)
    update_loss = exp_averager.apply([content_loss])

    return Network(
        content_loss=exp_averager.average(content_loss),
        gen_grads_and_vars=gen_grads_and_vars,
        gen_output=gen_output,
        train=tf.group(update_loss, incr_global_step, gen_train),
        global_step=global_step,
        learning_rate=learning_rate
    )


def save_images(fetches, FLAGS, step=None):
    image_dir = os.path.join(FLAGS.output_dir, "images")
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    filesets = []
    in_path = fetches['path_LR']
    name, _ = os.path.splitext(os.path.basename(str(in_path)))
    fileset = {"name": name, "step": step}

    if FLAGS.mode == 'inference':
        kind = "outputs"
        filename = name + ".png"
        if step is not None:
            filename = "%08d-%s" % (step, filename)
        fileset[kind] = filename
        out_path = os.path.join(image_dir, filename)
        contents = fetches[kind][0]
        with open(out_path, "wb") as f:
            f.write(contents)
        filesets.append(fileset)
    else:
        for kind in ["inputs", "outputs", "targets"]:
            filename = name + "-" + kind + ".png"
            if step is not None:
                filename = "%08d-%s" % (step, filename)
            fileset[kind] = filename
            out_path = os.path.join(image_dir, filename)
            contents = fetches[kind][0]
            with open(out_path, "wb") as f:
                f.write(contents)
        filesets.append(fileset)
    return filesets











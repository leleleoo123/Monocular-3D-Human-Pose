
"""Predicting 3d poses from 2d joints"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math
import os
import random
import sys
import time
import h5py
import copy

import matplotlib.pyplot as plt
import numpy as np
from six.moves import xrange  # pylint: disable=redefined-builtin
import tensorflow as tf

import linear_model
import data_pre

tf.app.flags.DEFINE_float("learning_rate", 1e-3, "Learning rate")
tf.app.flags.DEFINE_float("dropout", 1, "Dropout keep probability. 1 means no dropout")
tf.app.flags.DEFINE_integer("batch_size", 64, "Batch size to use during training")
tf.app.flags.DEFINE_integer("epochs", 200, "How many epochs we should train for")
tf.app.flags.DEFINE_boolean("camera_frame", False, "Convert 3d poses to camera coordinates")
tf.app.flags.DEFINE_boolean("max_norm", False, "Apply maxnorm constraint to the weights")
tf.app.flags.DEFINE_boolean("batch_norm", False, "Use batch_normalization")

# Data loading
tf.app.flags.DEFINE_boolean("predict_14", False, "predict 14 joints")
tf.app.flags.DEFINE_boolean("use_sh", False, "Use 2d pose predictions from StackedHourglass")

# Architecture
tf.app.flags.DEFINE_integer("linear_size", 1024, "Size of each model layer.")
tf.app.flags.DEFINE_integer("num_layers", 2, "Number of layers in the model.")
tf.app.flags.DEFINE_boolean("residual", False, "Whether to add a residual connection every 2 layers")

# Evaluation
tf.app.flags.DEFINE_boolean("evaluateActionWise",False, "The dataset to use either h36m or heva")

# Directories
tf.app.flags.DEFINE_string("cameras_path","data/h36m/cameras.h5","Directory to load camera parameters")
tf.app.flags.DEFINE_string("data_dir",   "data/h36m/", "Data directory")
tf.app.flags.DEFINE_string("train_dir", "experiments", "Training directory.")

# Train or load
tf.app.flags.DEFINE_boolean("use_cpu", False, "Whether to use the CPU")
tf.app.flags.DEFINE_integer("load", 0, "Try to load a previous checkpoint.")

# Misc
tf.app.flags.DEFINE_boolean("use_fp16", False, "Train using fp16 instead of fp32.")

FLAGS = tf.app.flags.FLAGS

train_dir = os.path.join( FLAGS.train_dir,
  'dropout_{0}'.format(FLAGS.dropout),
  'epochs_{0}'.format(FLAGS.epochs) if FLAGS.epochs > 0 else '',
  'lr_{0}'.format(FLAGS.learning_rate),
  'residual' if FLAGS.residual else 'not_residual',
  'depth_{0}'.format(FLAGS.num_layers),
  'linear_size{0}'.format(FLAGS.linear_size),
  'batch_size_{0}'.format(FLAGS.batch_size),
  'maxnorm' if FLAGS.max_norm else 'no_maxnorm',
  'batch_normalization' if FLAGS.batch_norm else 'no_batch_normalization',
  'predict_14' if FLAGS.predict_14 else 'predict_17')

print( train_dir )
summaries_dir = os.path.join( train_dir, "log" ) # Directory for TB summaries

# To avoid race conditions: https://github.com/tensorflow/tensorflow/issues/7448
os.system('mkdir -p {}'.format(summaries_dir))

def create_model( session, batch_size ):
  """
  Create model and initialize it or load its parameters in a session

  Args
    session: tensorflow session
    actions: list of string. Actions to train/test on
    batch_size: integer. Number of examples in each batch
  Returns
    model: The created (or loaded) model
  Raises
    ValueError if asked to load a model, but the checkpoint specified by
    FLAGS.load cannot be found.
  """

  model = linear_model.LinearModel(
      FLAGS.linear_size,
      FLAGS.num_layers,
      FLAGS.residual,
      FLAGS.batch_norm,
      FLAGS.max_norm,
      batch_size,
      FLAGS.learning_rate,
      summaries_dir,
      FLAGS.predict_14,
      dtype=tf.float16 if FLAGS.use_fp16 else tf.float32)
   

  if FLAGS.load <= 0:
    # Create a new model from scratch
    print("Creating model with fresh parameters.")
    session.run( tf.global_variables_initializer() )
    return model

  # Load a previously saved model
  ckpt = tf.train.get_checkpoint_state( train_dir, latest_filename="checkpoint")
  print( "train_dir", train_dir )

  if ckpt and ckpt.model_checkpoint_path:
    # Check if the specific checkpoint exists
    if FLAGS.load > 0:
      if os.path.isfile(os.path.join(train_dir,"checkpoint-{0}.index".format(FLAGS.load))):
        ckpt_name = os.path.join( os.path.join(train_dir,"checkpoint-{0}".format(FLAGS.load)) )
      else:
        raise ValueError("Asked to load checkpoint {0}, but it does not seem to exist".format(FLAGS.load))
    else:
      ckpt_name = os.path.basename( ckpt.model_checkpoint_path )

    print("Loading model {0}".format( ckpt_name ))
    model.saver.restore( session, ckpt.model_checkpoint_path )
    return model
  else:
    print("Could not find checkpoint. Aborting.")
    raise( ValueError, "Checkpoint {0} does not seem to exist".format( ckpt.model_checkpoint_path ) )

  return model

def train():
  """Train a linear model for 3d pose estimation"""
  """
  actions = data_utils.define_actions( FLAGS.action )

  number_of_actions = len( actions )

  # Load camera parameters
  SUBJECT_IDS = [1,5,6,7,8,9,11]
  rcams = cameras.load_cameras(FLAGS.cameras_path, SUBJECT_IDS)
  """
  # my code start of load unity data
  train_in_data, train_in_frame, train_in_myjoint = data_pre.load_pose(True, 'data/2d_left/')
  train_in_cam_data = data_pre.root_data(train_in_data)
  train_in_data_mean, train_in_data_std = data_pre.normalizeStats(train_in_data)
  train_in_data_norm = data_pre.normalizeData(train_in_data, train_in_data_mean, train_in_data_std, train_in_frame)

  train_out_data, train_out_frame, train_out_myjoint = data_pre.load_pose(True, 'data/2d_right/')
  train_out_data = data_pre.root_data(train_out_data)
  train_out_data_mean, train_out_data_std = data_pre.normalizeStats(train_out_data)
  train_out_data_norm = data_pre.normalizeData(train_out_data, train_out_data_mean, train_out_data_std, train_out_frame)

  test_in_data, test_in_frame, test_in_myjoint = data_pre.load_pose(False, 'data/2d_left/')
  test_in_data = data_pre.root_data(test_in_data)
  test_in_data_norm = data_pre.normalizeData(test_in_data, train_in_data_mean, train_in_data_std, test_in_frame)

  test_out_data, test_out_frame, test_out_myjoint = data_pre.load_pose(False, 'data/2d_right/')
  test_out_data = data_pre.root_data(test_out_data)
  test_out_data_norm = data_pre.normalizeData(test_out_data,train_out_data_mean, train_out_data_std, test_out_frame)
 
 
  # Load 3d data and load (or create) 2d projections
  # train_set_3d, test_set_3d, data_mean_3d, data_std_3d, dim_to_ignore_3d, dim_to_use_3d, train_root_positions, test_root_positions = data_utils.read_3d_data(
  #   actions, FLAGS.data_dir, FLAGS.camera_frame, rcams, FLAGS.predict_14 )
  
  # my code here replace as unity data
  train_set_3d = train_out_data_norm
  test_set_3d = test_out_data_norm

  '''
  # Read stacked hourglass 2D predictions if use_sh, otherwise use groundtruth 2D projections
  if FLAGS.use_sh:
    train_set_2d, test_set_2d, data_mean_2d, data_std_2d, dim_to_ignore_2d, dim_to_use_2d = data_utils.read_2d_predictions(actions, FLAGS.data_dir)
  else:
    
     train_set_2d, test_set_2d, data_mean_2d, data_std_2d, dim_to_ignore_2d, dim_to_use_2d = data_utils.create_2d_data( actions, FLAGS.data_dir, rcams )
    '''
  
  # replace as unity data
  train_set_2d = train_in_data_norm
  test_set_2d = test_in_data_norm

  print( "done reading and normalizing data." )

  # Avoid using the GPU if requested
  device_count = {"GPU": 0} if FLAGS.use_cpu else {"GPU": 1}
  with tf.Session(config=tf.ConfigProto(
    device_count=device_count,
    allow_soft_placement=True )) as sess:

    # === Create the model ===
    print("Creating %d bi-layers of %d units." % (FLAGS.num_layers, FLAGS.linear_size))
    model = create_model( sess, FLAGS.batch_size )
    model.train_writer.add_graph( sess.graph )
    print("Model created")

    #=== This is the training loop ===
    step_time, loss, val_loss = 0.0, 0.0, 0.0
    current_step = 0 if FLAGS.load <= 0 else FLAGS.load + 1
    previous_losses = []

    step_time, loss = 0, 0
    current_epoch = 0
    log_every_n_batches = 1000

    for _ in xrange( FLAGS.epochs ):
      current_epoch = current_epoch + 1

      # === Load training batches for one epoch ===
      encoder_inputs, decoder_outputs = data_pre.get_all_batches( train_set_2d, train_set_3d, train_in_frame, FLAGS.batch_size, training=True )
      print('done reading and normalizing unity  training data...')
      nbatches = len( encoder_inputs )
      print("There are {0} train batches".format( nbatches ))
      start_time, loss = time.time(), 0.

      # === Loop through all the training batches ===
      for i in range( nbatches ):
        if (i+1) % log_every_n_batches == 0:
          # Print progress every log_every_n_batches batches
          print("Working on epoch {0}, batch {1} / {2}... ".format( current_epoch, i+1, nbatches), end="" )
        enc_in, dec_out = encoder_inputs[i], decoder_outputs[i]
        step_loss, loss_summary, lr_summary, _ =  model.step( sess, enc_in, dec_out, FLAGS.dropout, isTraining=True )

        if (i+1) % log_every_n_batches == 0:
          # Log and print progress every log_every_n_batches batches
          model.train_writer.add_summary( loss_summary, current_step )
          model.train_writer.add_summary( lr_summary, current_step )
          step_time = (time.time() - start_time)
          start_time = time.time()
          print("done in {0:.2f} ms".format( 1000*step_time / log_every_n_batches ) )

        loss += step_loss
        current_step += 1
        # === end looping through training batches ===

      loss = loss / nbatches
      print("=============================\n"
            "Global step:         %d\n"
            "Learning rate:       %.2e\n"
            "Train loss avg:      %.4f\n"
            "=============================" % (model.global_step.eval(),
            model.learning_rate.eval(), loss) )
      # === End training for an epoch ===

      # === Testing after this epoch ===

      if FLAGS.evaluateActionWise:

        print("start testing of piexl") # line of 30 equal signs
        cum_err = 0
        dp = 1.0
       
        # Get 2d and 3d testing data for this action
        action_test_set_2d = test_set_2d
        action_test_set_3d = test_set_3d
        encoder_inputs, decoder_outputs = data_pre.get_all_batches( action_test_set_2d, action_test_set_3d, test_in_frame, FLAGS.batch_size, training=False)
        print('done reading and normalizing unity testing data...')

        all_dists, start_time, loss = [], time.time(), 0.
        nbatches = len( encoder_inputs )
        log_every_n_batches = 1000
        count = 0
        count_all = 0
        for i in range(nbatches):

          if current_epoch > 0 and (i+1) % log_every_n_batches == 0:
            print("Working on test epoch {0}, batch {1} / {2}...".format( current_epoch, i+1, nbatches) )

          enc_in, dec_out = encoder_inputs[i], decoder_outputs[i]
          dp = 1.0 # dropout keep probability is always 1 at test time
          step_loss, loss_summary, poses3d = model.step( sess, enc_in, dec_out, dp, isTraining=False )
          loss += step_loss

          # denormalize
          enc_in  = data_pre.unNormalizeData( enc_in, train_in_data_mean, train_in_data_std )
          dec_out = data_pre.unNormalizeData( dec_out, train_out_data_mean, train_out_data_std )
          poses3d = data_pre.unNormalizeData( poses3d, train_out_data_mean, train_out_data_std )
          
          # Compute Euclidean distance error per joint
          heads = np.zeros( (dec_out.shape[0],1) )
          sqerr = np.zeros( (dec_out.shape[0],34) )
          for i in range(dec_out.shape[0]):
            heads[i,0] = np.sqrt((dec_out[i,0] - dec_out[i,1]) ** 2 + (dec_out[i,17] - dec_out[i,18]) ** 2)

          for i in range(sqerr.shape[0]): 
            for j in range(34):
              sqerr[i,j] = (poses3d[i,j] - dec_out[i,j]) ** 2 

          dists = np.zeros( (sqerr.shape[0], 17) ) # Array with L2 error per joint in piexl
          for i in range(sqerr.shape[0]): 
            for j in range(17):
              dists[i,j] = np.sqrt(sqerr[i,j]+sqerr[i,j+17])
          cnt = 0
          for i in range(sqerr.shape[0]):
            for j in range(17):
              if dists[i,j] < heads[i,0] * 0.5:
                cnt += 1
          count += cnt
          count_all += sqerr.shape[0] * 17

        print('='*50)
        print(count)
        print(count_all)
        pck = int(count)/int(count_all)
        print('PCKH@0.5 of testing is :%.4f'%pck)
        print('='*50)

      # Save the model
      print( "Saving the model... ", end="" )
      start_time = time.time()
      model.saver.save(sess, os.path.join(train_dir, 'checkpoint'), global_step=current_step )
      print( "done in {0:.2f} ms".format(1000*(time.time() - start_time)) )

      # Reset global time and loss
      step_time, loss = 0, 0

      sys.stdout.flush()


def main(_):
  train()


if __name__ == "__main__":
  tf.app.run()
  



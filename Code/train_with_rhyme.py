#!/usr/bin/env python
# -*- coding:utf-8 -*-

from __future__ import print_function
import numpy as np
import tensorflow as tf

import argparse
import time
import os,sys
from six.moves import cPickle

from utils import TextLoader
from model_with_rhyme import Model

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--save_dir', type=str, default='save',
                       help='directory to store checkpointed models')
    parser.add_argument('--rnn_size', type=int, default=64,
                       help='size of RNN hidden state')
    parser.add_argument('--num_layers', type=int, default=2,
                       help='number of layers in the RNN')
    parser.add_argument('--model', type=str, default='lstm',
                       help='rnn, gru, or lstm')
    parser.add_argument('--batch_size', type=int, default=64,
                       help='minibatch size')
    parser.add_argument('--num_epochs', type=int, default=50,
                       help='number of epochs')
    parser.add_argument('--save_every', type=int, default=1000,
                       help='save frequency')
    parser.add_argument('--grad_clip', type=float, default=5.,
                       help='clip gradients at this value')
    parser.add_argument('--learning_rate', type=float, default=0.002,
                       help='learning rate')
    parser.add_argument('--decay_rate', type=float, default=0.97,
                       help='decay rate for rmsprop')
    parser.add_argument('--dropout', type=float, default=1,
                        help='keep out rate for rnn')
    parser.add_argument('--init_from', type=str, default=None,
                       help="""continue training from saved model at this path. Path must contain files saved by previous training process:
                            'config.pkl'        : configuration;
                            'chars_vocab.pkl'   : vocabulary definitions;
                            'iterations'        : number of trained iterations;
                            'losses-*'          : train loss;
                            'checkpoint'        : paths to model file(s) (created by tf).
                                                  Note: this file contains absolute paths, be careful when moving files around;
                            'model.ckpt-*'      : file(s) with model definition (created by tf)
                        """)
    args = parser.parse_args()
    train(args)


def train(args):
    data_loader = TextLoader(args.batch_size)
    args.poem_length = data_loader.poem_length
    #self.rhymes[ID] = self.rhyme_set.index(rhyme)
    print("Maximal length:",args.poem_length)

    print('finish readling file ...\n')

    args.vocab_size = data_loader.vocab_size


    print("Capture Rules Suceessfully")


    # check compatibility if training is continued from previously saved model
    if args.init_from is not None:
        # check if all necessary files exist
        assert os.path.isdir(args.init_from)," %s must be a a path" % args.init_from
        assert os.path.isfile(os.path.join(args.init_from,"config.pkl")),"config.pkl file does not exist in path %s"%args.init_from
        assert os.path.isfile(os.path.join(args.init_from,"chars_vocab.pkl")),"chars_vocab.pkl.pkl file does not exist in path %s" % args.init_from
        ckpt = tf.train.get_checkpoint_state(args.init_from)
        assert ckpt,"No checkpoint found"
        assert ckpt.model_checkpoint_path,"No model path found in checkpoint"
        assert os.path.isfile(os.path.join(args.init_from,"iterations")),"iterations file does not exist in path %s " % args.init_from

        # open old config and check if models are compatible
        with open(os.path.join(args.init_from, 'config.pkl'),'rb') as f:
            saved_model_args = cPickle.load(f)
        need_be_same=["model","rnn_size","num_layers"]
        for checkme in need_be_same:
            assert vars(saved_model_args)[checkme]==vars(args)[checkme],"Command line argument and saved model disagree on '%s' "%checkme

        # open saved vocab/dict and check if vocabs/dicts are compatible
        with open(os.path.join(args.init_from, 'chars_vocab.pkl'),'rb') as f:
            saved_chars, saved_vocab, saved_rhymes = cPickle.load(f)

        assert saved_chars==data_loader.chars, "Data and loaded model disagree on character set!"
        assert saved_vocab==data_loader.vocab, "Data and loaded model disagree on dictionary mappings!"
        assert saved_rhymes==data_loader.rhymes, "Data and loaded model disagree on rhyme mappings!"


    with open(os.path.join(args.save_dir, 'config.pkl'), 'wb') as f:
        cPickle.dump(args, f)
    with open(os.path.join(args.save_dir, 'chars_vocab.pkl'), 'wb') as f:
        cPickle.dump((data_loader.chars, data_loader.vocab, data_loader.rhymes), f)

    model = Model(args)

    def duplicate(x):
        i,j = x.shape
        k = 2
        xx = np.empty([i,j,k])
        for ii in range(i):
            for jj in range(j):
                for kk in range(k):
                    xx[i,j,k] = x[i,j]
        return xx

    with tf.Session() as sess:
        tf.global_variables_initializer().run()
        saver = tf.train.Saver(tf.global_variables())
        iterations = 0
        # restore model and number of iterations
        if args.init_from is not None:
            saver.restore(sess, ckpt.model_checkpoint_path)
            with open(os.path.join(args.save_dir, 'iterations'),'rb') as f:
                iterations = cPickle.load(f)
        losses = []
        for e in range(args.num_epochs):
            sess.run(tf.assign(model.lr, args.learning_rate * (args.decay_rate ** e)))
            data_loader.reset_batch_pointer()
            for b in range(data_loader.num_batches):
                iterations += 1
                start = time.time()
                xdata, ydata, xrhyme, yrhyme = data_loader.next_batch()

                #xx = duplicate(x)
                #yy = duplicate(y)

                #feed = {model.input_data: xx,
                #        model.targets: yy}

                feed = {model.input_data: xdata,
                        model.input_rhyme: xrhyme,
                        model.target_data: ydata}

                train_loss, _ , _ = sess.run(
                    [model.cost, model.final_state, model.train_op],
                    feed)
                end = time.time()
                sys.stdout.write('\r')
                info = "{}/{} (epoch {}), train_loss = {:.3f}, time/batch = {:.3f}" \
                    .format(e * data_loader.num_batches + b,
                            args.num_epochs * data_loader.num_batches,
                            e, train_loss, end - start)
                sys.stdout.write(info)
                sys.stdout.flush()
                losses.append(train_loss)
                if (e * data_loader.num_batches + b) % args.save_every == 0\
                    or (e==args.num_epochs-1 and b == data_loader.num_batches-1): # save for the last result
                    checkpoint_path = os.path.join(args.save_dir, 'model.ckpt')
                    saver.save(sess, checkpoint_path, global_step = iterations)
                    with open(os.path.join(args.save_dir,"iterations"),'wb') as f:
                        cPickle.dump(iterations,f)
                    with open(os.path.join(args.save_dir,"losses-"+str(iterations)),'wb') as f:
                        cPickle.dump(losses,f)
                    losses = []
                    sys.stdout.write('\n')
                    print("model saved to {}".format(checkpoint_path))
            sys.stdout.write('\n')

if __name__ == '__main__':
    main()
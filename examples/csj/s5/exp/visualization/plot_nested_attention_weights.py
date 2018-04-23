#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Plot attention weights of the nested attention model (CSJ corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath, isdir
import sys
import argparse
import shutil
import numpy as np

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
plt.style.use('ggplot')
import seaborn as sns
sns.set_style("white")
blue = '#4682B4'
orange = '#D2691E'
green = '#006400'

# sns.set(font='IPAMincho')
sns.set(font='Noto Sans CJK JP')

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.csj.s5.exp.dataset.load_dataset_hierarchical import Dataset
from utils.io.labels.character import Idx2char
from utils.io.labels.word import Idx2word
from utils.directory import mkdir_join, mkdir
from utils.visualization.attention import plot_hierarchical_attention_weights
from utils.config import load_config

parser = argparse.ArgumentParser()
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--max_decode_len', type=int, default=80,
                    help='the length of output sequences to stop prediction when EOS token have not been emitted')
parser.add_argument('--max_decode_len_sub', type=int, default=150,
                    help='the length of output sequences to stop prediction when EOS token have not been emitted')
parser.add_argument('--data_save_path', type=str, help='path to saved data')


def main():

    args = parser.parse_args()

    # Load a config file (.yml)
    params = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Load dataset
    test_data = Dataset(
        data_save_path=args.data_save_path,
        backend=params['backend'],
        input_channel=params['input_channel'],
        use_delta=params['use_delta'],
        use_double_delta=params['use_double_delta'],
        data_type='eval1',
        # data_type='eval2',
        # data_type='eval3',
        data_size=params['data_size'],
        label_type=params['label_type'], label_type_sub=params['label_type_sub'],
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, reverse=False, tool=params['tool'])

    params['num_classes'] = test_data.num_classes
    params['num_classes_sub'] = test_data.num_classes_sub

    # Load model
    model = load(model_type=params['model_type'],
                 params=params,
                 backend=params['backend'])

    # Restore the saved parameters
    model.load_checkpoint(save_path=args.model_path, epoch=args.epoch)

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    # Visualize
    plot(model=model,
         dataset=test_data,
         max_decode_len=args.max_decode_len,
         max_decode_len_sub=args.max_decode_len_sub,
         eval_batch_size=args.eval_batch_size,
         save_path=mkdir_join(args.model_path, 'att_weights'))
    # save_path=None)


def plot(model, dataset, max_decode_len, max_decode_len_sub,
         eval_batch_size=None, save_path=None):
    """Visualize attention weights of Attetnion-based model.
    Args:
        model: model to evaluate
        dataset: An instance of a `Dataset` class
        max_decode_len (int): the length of output sequences
            to stop prediction when EOS token have not been emitted.
        max_decode_len_sub (int):
        eval_batch_size (int, optional): the batch size when evaluating the model
        save_path (string, optional): path to save attention weights plotting
    """
    # Clean directory
    if save_path is not None and isdir(save_path):
        shutil.rmtree(save_path)
        mkdir(save_path)

    idx2word = Idx2word(dataset.vocab_file_path, return_list=True)
    idx2char = Idx2char(dataset.vocab_file_path_sub, return_list=True)

    for batch, is_new_epoch in dataset:

        if model.model_type == 'nested_attention':
            best_hyps, best_hyps_sub, aw, aw_sub, aw_dec_out_sub, gate_weights = model.attention_weights(
                batch['xs'], batch['x_lens'],
                max_decode_len=max_decode_len,
                max_decode_len_sub=max_decode_len_sub)
        else:
            raise ValueError

        for b in range(len(batch['xs'])):

            # Check if the sum of attention weights equals to 1
            # print(np.sum(aw[b], axis=1))

            word_list = idx2word(best_hyps[b])
            char_list = idx2char(best_hyps_sub[b])

            # TODO: eosで区切ってもattention weightsは打ち切られていない．

            speaker = batch['input_names'][b].split('_')[0]

            # word to acoustic & character to acoustic
            plot_hierarchical_attention_weights(
                aw[b, :len(word_list), :batch['x_lens'][b]],
                aw_sub[b, :len(char_list), :batch['x_lens'][b]],
                label_list=word_list,
                label_list_sub=char_list,
                spectrogram=batch['xs'][b, :, :dataset.input_channel],
                save_path=mkdir_join(save_path, speaker,
                                     batch['input_names'][b] + '.png'),
                figsize=(40, 8)
            )

            # word to characater
            plot_word2char_attention_weights(
                aw_dec_out_sub[b, :len(word_list), :len(char_list)],
                label_list=word_list,
                label_list_sub=char_list,
                save_path=mkdir_join(save_path, speaker,
                                     batch['input_names'][b] + '_word2char.png'),
                figsize=(40, 8)
            )

            # gate activation
            if gate_weights is not None:
                plt.clf()
                plt.figure(figsize=(40, 8))
                plt.plot(np.arange(0, len(gate_weights[b])), np.mean(
                    gate_weights[b], axis=1), 1)
                plt.xlabel('Output words', fontsize=12)
                plt.xticks(np.arange(0, len(gate_weights[b])), word_list)
                plt.savefig(join(save_path, speaker,
                                 batch['input_names'][b] + '_gate.png'), dvi=500)
                plt.close()

        if is_new_epoch:
            break


def plot_word2char_attention_weights(attention_weights, label_list, label_list_sub,
                                     save_path=None, figsize=(10, 4)):
    """Plot attention weights from word-level decoder to character-level decoder.
    Args:
        attention_weights (np.ndarray): A tensor of size `[T_out, T_in]`
        label_list (list):
        label_list_sub (list):
        save_path (string): path to save a figure of CTC posterior (utterance)
        figsize (tuple):
    """
    plt.clf()
    plt.figure(figsize=figsize)

    # Plot attention weights
    sns.heatmap(attention_weights,
                # cmap='Blues',
                cmap='viridis',
                xticklabels=label_list_sub,
                yticklabels=label_list)
    # cbar_kws={"orientation": "horizontal"}
    plt.ylabel('Output characters (→)', fontsize=12)
    plt.ylabel('Output words (←)', fontsize=12)
    plt.yticks(rotation=0)
    plt.xticks(rotation=0)

    # Save as a png file
    if save_path is not None:
        plt.savefig(save_path, dvi=500)

    plt.close()


if __name__ == '__main__':
    main()

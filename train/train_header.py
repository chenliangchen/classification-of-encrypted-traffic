import tensorflow as tf
from tf import tf_utils as tfu, confusionmatrix as conf, dataset
import numpy as np
import datetime
from sklearn import metrics
import utils

now = datetime.datetime.now()
subdir = "/%.2d%.2d_%.2d%.2d" % (now.day, now.month, now.hour, now.minute)
summaries_dir = '../tensorboard'
num_headers = 16
hidden_units = 15
train_dirs = ['E:/Data/windows/no_checksum/{0}/'.format(num_headers), 'E:/Data/linux/no_checksum/{0}/'.format(num_headers), 'E:/Data/salik_windows_extended/no_checksum/{0}/'.format(num_headers)]
test_dirs = ['E:/Data/windows_chrome/no_checksum/{0}/'.format(num_headers)]

save_dir = "../trained_models/"
seed = 0

# Beta for L2 regularization
beta = 1.0

input_size = num_headers*54
data = dataset.read_data_sets(train_dirs, test_dirs, merge_data=False, one_hot=True, validation_size=0.1, test_size=0.2,
                              balance_classes=False,
                              payload_length=input_size, seed=seed)
tf.reset_default_graph()
num_classes = len(dataset._label_encoder.classes_)
labels = dataset._label_encoder.classes_

cm = conf.ConfusionMatrix(num_classes, class_names=labels)
gpu_opts = tf.GPUOptions(per_process_gpu_memory_fraction=0.45)

x_pl = tf.placeholder(tf.float32, [None, input_size], name='xPlaceholder')
y_pl = tf.placeholder(tf.float64, [None, num_classes], name='yPlaceholder')
y_pl = tf.cast(y_pl, tf.float32)

x = tfu.ffn_layer('layer1', x_pl, hidden_units, activation=tf.nn.relu, seed=seed)
# x = tf.layers.dense(x_pl, hidden_units, tf.nn.relu)
# x = tfu.dropout(x, 0.5)
# x = tfu.ffn_layer('layer2', x, hidden_units, activation=tf.nn.relu)
# x = tfu.ffn_layer('layer2', x, 50, activation=tf.nn.sigmoid)
# x = tfu.ffn_layer('layer3', x, 730, activation=tf.nn.relu)
y = tfu.ffn_layer('output_layer', x, hidden_units=num_classes, activation=tf.nn.softmax, seed=seed)
y_ = tf.argmax(y, axis=1)
# with tf.name_scope('cross_entropy'):
#   # The raw formulation of cross-entropy,
#   #
#   # tf.reduce_mean(-tf.reduce_sum(y_ * tf.log(tf.softmax(y)),
#   #                               reduction_indices=[1]))
#   #
#   # can be numerically unstable.
#   #
#   # So here we use tf.losses.sparse_softmax_cross_entropy on the
#   # raw logit outputs of the nn_layer above.
#   with tf.name_scope('total'):
#     cross_entropy = tf.losses.softmax_cross_entropy(onehot_labels=y_pl, logits=y)


with tf.variable_scope('loss'):
    # computing cross entropy per sample
    cross_entropy = -tf.reduce_sum(y_pl * tf.log(y + 1e-8), reduction_indices=[1])

    W1 = tf.get_default_graph().get_tensor_by_name("layer1/W:0")
    loss = tf.nn.l2_loss(W1)
    # averaging over samples
    cross_entropy = tf.reduce_mean(cross_entropy)
    loss = tf.reduce_mean(cross_entropy + loss * beta)

tf.summary.scalar('cross_entropy', cross_entropy)

with tf.variable_scope('training'):
    # defining our optimizer
    optimizer = tf.train.AdamOptimizer(learning_rate=0.001)

    # applying the gradients
    train_op = optimizer.minimize(cross_entropy)

with tf.variable_scope('performance'):
    # making a one-hot encoded vector of correct (1) and incorrect (0) predictions
    correct_prediction = tf.equal(tf.argmax(y, axis=1), tf.argmax(y_pl, axis=1))

    # averaging the one-hot encoded vector
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

tf.summary.scalar('accuracy', accuracy)

# Merge all the summaries and write them out
merged = tf.summary.merge_all()
train_writer = tf.summary.FileWriter(summaries_dir + '/train/' + subdir)
val_writer = tf.summary.FileWriter(summaries_dir + '/validation/' + subdir)
test_writer = tf.summary.FileWriter(summaries_dir + '/test/' + subdir)

# Training Loop
batch_size = 100
max_epochs = 20

valid_loss, valid_accuracy = [], []
train_loss, train_accuracy = [], []
test_loss, test_accuracy = [], []

with tf.Session() as sess:
    train_writer.add_graph(sess.graph)
    sess.run(tf.global_variables_initializer())
    print('Begin training loop')
    saver = tf.train.Saver()
    try:
        while data.train.epochs_completed < max_epochs:
            _train_loss, _train_accuracy = [], []

            ## Run train op
            x_batch, y_batch = data.train.next_batch(batch_size)
            fetches_train = [train_op, cross_entropy, accuracy, merged]
            feed_dict_train = {x_pl: x_batch, y_pl: y_batch}
            _, _loss, _acc, _summary = sess.run(fetches_train, feed_dict_train)

            _train_loss.append(_loss)
            _train_accuracy.append(_acc)
            ## Compute validation loss and accuracy
            if data.train.epochs_completed % 1 == 0 \
                    and data.train._index_in_epoch <= batch_size:

                train_writer.add_summary(_summary, data.train.epochs_completed)

                train_loss.append(np.mean(_train_loss))
                train_accuracy.append(np.mean(_train_accuracy))

                fetches_valid = [cross_entropy, accuracy, merged]

                feed_dict_valid = {x_pl: data.validation.payloads, y_pl: data.validation.labels}
                _loss, _acc, _summary = sess.run(fetches_valid, feed_dict_valid)

                valid_loss.append(_loss)
                valid_accuracy.append(_acc)
                val_writer.add_summary(_summary, data.train.epochs_completed)
                print(
                    "Epoch {} : Train Loss {:6.3f}, Train acc {:6.3f},  Valid loss {:6.3f},  Valid acc {:6.3f}".format(
                        data.train.epochs_completed, train_loss[-1], train_accuracy[-1], valid_loss[-1],
                        valid_accuracy[-1]))
        test_epoch = data.test.epochs_completed
        while data.test.epochs_completed == test_epoch:
            batch_size = 1000
            x_batch, y_batch = data.test.next_batch(batch_size)
            feed_dict_test = {x_pl: x_batch, y_pl: y_batch}
            _loss, _acc, _summary = sess.run(fetches_valid, feed_dict_test)
            y_preds = sess.run(fetches=y, feed_dict=feed_dict_test)
            y_preds = tf.argmax(y_preds, axis=1).eval()
            y_true = tf.argmax(y_batch, axis=1).eval()
            cm.batch_add(y_true, y_preds)
            test_loss.append(_loss)
            test_accuracy.append(_acc)
            # test_writer.add_summary(_summary, data.train.epochs_completed)
        print('Test Loss {:6.3f}, Test acc {:6.3f}'.format(
            np.mean(test_loss), np.mean(test_accuracy)))
        saver.save(sess, save_dir+'header_{0}_{1}_units.ckpt'.format(num_headers, hidden_units))
        feed_dict_test = {x_pl: data.test.payloads, y_pl: data.test.labels}
        y_preds = sess.run(fetches=y_, feed_dict=feed_dict_test)
        y_true = tf.argmax(data.test.labels, axis=1).eval()
        y_true = [labels[i] for i in y_true]
        y_preds = [labels[i] for i in y_preds]
        nostream_dict = ['http', 'https']
        y_stream_true = []
        y_stream_preds = []
        for i,v in enumerate(y_true):
            pred = y_preds[i]
            if v in nostream_dict:
                y_stream_true.append('No Streaming')
            else:
                y_stream_true.append('Streaming')
            if pred in nostream_dict:
                y_stream_preds.append('No Streaming')
            else:
                y_stream_preds.append('Streaming')
        conf1 = metrics.confusion_matrix(y_true, y_preds, labels=labels)
        conf2 = metrics.confusion_matrix(y_stream_true, y_stream_preds, labels=['No Streaming', 'Streaming'])

    except KeyboardInterrupt:
        pass

utils.plot_confusion_matrix(conf1, labels, save=True, title="AllClasses")
utils.plot_confusion_matrix(conf2, ['No Streaming', 'Streaming'], save=True, title="StreamNoStream")


# print(cm)


#
# # df = utils.load_h5(dir + filename+'.h5', key=filename.split('-')[0])
# # print("Load done!")
# # print(df.shape)
# # payloads = df['payload'].values
# # payloads = utils.pad_elements_with_zero(payloads)
# # df['payload'] = payloads
# #
# # # Converting hex string to list of int... Maybe takes to long?
# # payloads = [[int(i, 16) for i in list(x)] for x in payloads]
# # np_payloads = numpy.array(payloads)
# # # dataset = DataSet(np_payloads, df['label'].values)
# # x, y = dataset.next_batch(10)
# # batch_size = 100
# # features = {'payload': payloads}
# #
# #
# # gb = df.groupby(['ip.dst', 'ip.src', 'port.dst', 'port.src'])
# #
# #
# # l = dict(list(gb))
# #
# #
# # s = [[k, len(v)] for k, v in sorted(l.items(), key=lambda x: len(x[1]), reverse=True)]
#
#
# print("DONE")

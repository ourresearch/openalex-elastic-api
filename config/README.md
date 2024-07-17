# config files adapted from openalex-gui (javascript to python)

## `property_config.py`

adapted from https://github.com/ourresearch/openalex-gui/blob/8c01677c30104bf994c841fe9597ad0af6631a4b/src/facetConfigs.js#L58-L59

first step: fed the objects in chunks of about 300 lines to chatgpt, giving the prompt each time:

```
I'm going to give you a chunk of javascript code. Please convert it from javascript to python. Follow these rules strictly:
1. keep all variable names the same. 
2. don't convert arrow javascript functions for the field "extractFn". just keep them as strings. 
3. keep all the comments as they are in the original code.
4. preserve the order of all lists.
```

Then used python (in a notebook) to make additional changes such as adding additional fields and deleting certain fields.


## `entity_config.py`

adapted from https://github.com/ourresearch/openalex-gui/blob/f30c0e8b0c858914c1c79cbcd6d31f6e7b1e0ecf/src/entityConfigs.js#L0-L1

converted to a list of objects with "id" fields. did the conversion to Python manually using text editor macros